#!/usr/bin/env python3
"""
北京总厂日稽核问题分析报告 - 数据刷新脚本（本机执行）

工作方式：
  本机通过企业微信 CLI（wecom-cli，扫码登录，无需管理后台）从智能表格拉取数据，
  再推送到 Cloudflare 的 /api/update 接口写入 KV，网页加载时自动读取 KV。

为什么走本地而不是服务端：
  服务端自动刷新需要企微自建应用的 Secret（WECOM_AGENT_SECRET），而该 Secret
  只能在企业微信管理后台获取。若无法进入管理后台，服务端刷新不可用，只能由本机
  脚本（用你本人企微账号扫码授权）完成取数并推送。

前置条件：
  1. 安装 CLI：npm install -g @wecom/cli
  2. 授权（仅需一次，用企业微信扫码）：wecom-cli auth init --noninteractive
  3. 推送密码（与 Cloudflare 环境变量 password / PASSWORD 一致）：
       环境变量 QA_PUSH_PASSWORD，或同目录 config.json 写 {"password":"..."}

运行：
  python refresh_report.py

定时（Windows 任务计划程序）：
  - 搜索“任务计划程序” → 创建基本任务 → 触发器每天 → 操作启动程序
  - 程序：python  参数：refresh_report.py  起始于：脚本所在目录
定时（Mac/Linux crontab）：
  0 8 * * * cd /path/to/脚本目录 && python refresh_report.py
"""

import os, json, subprocess, sys
from datetime import datetime
from collections import Counter

# ============ 按需修改 ============
API_URL = "https://want-quality-report.pages.dev"
DOCID = "s3_AG4A_waWABECNJmGuMZYOQwujgdTe"   # 智能表格 docid（前缀 s3_）

# 推送密码（与 Cloudflare 环境变量 password / PASSWORD 一致）
_cfg_password = ""
try:
    with open(os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8") as _f:
        _cfg_password = json.load(_f).get("password", "")
except Exception:
    _cfg_password = ""
PASSWORD = os.environ.get("QA_PUSH_PASSWORD") or _cfg_password
if not PASSWORD:
    print("错误：未找到推送密码。请二选一：")
    print("  ① 设置环境变量：set QA_PUSH_PASSWORD=你的密码")
    print("  ② 在同目录创建 config.json：{\"password\": \"你的密码\"}")
    print("  该密码必须与 Cloudflare 环境变量 password（或 PASSWORD）一致。")
    sys.exit(1)
# =================================


def detect_cli():
    """自动探测可用的企微 CLI 二进制（优先 wecom-cli，兼容 wecom）。"""
    for cand in ("wecom-cli", "wecom"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, text=True, timeout=10)
            return cand
        except (FileNotFoundError, OSError):
            continue
    return None


def run_cli(sub, payload):
    """调用 wecom-cli 子命令，payload 为 dict，返回解析后的 JSON 或 None。"""
    cli = detect_cli()
    if not cli:
        print("  ❌ 未找到企微 CLI。请先安装：npm install -g @wecom/cli")
        print("     并授权：wecom-cli auth init --noninteractive（用企业微信扫码）")
        return None
    js = json.dumps(payload, ensure_ascii=False)
    # 以参数列表方式调用，避免 Windows / Linux 引号差异
    try:
        r = subprocess.run([cli, "smartsheet", sub, "--json", js],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  ⚠ 命令超时：smartsheet {sub}")
        return None
    if r.returncode != 0:
        print(f"  ⚠ 命令失败（{sub}）：{r.stderr.strip()[:300]}")
        return None
    return parse_json_output(r.stdout)


def parse_json_output(out):
    out = (out or "").strip()
    if not out:
        return None
    # 大结果可能写入临时文件并返回绝对路径
    if (out.startswith("/") or (len(out) > 2 and out[1] == ":")) and os.path.isfile(out):
        try:
            with open(out, encoding="utf-8") as f:
                out = f.read()
        except Exception:
            return None
    # 取第一个 JSON 对象（忽略尾部日志/换行）
    try:
        return json.JSONDecoder().raw_decode(out)[0]
    except Exception:
        i = out.find("{")
        if i >= 0:
            try:
                return json.JSONDecoder().raw_decode(out[i:])[0]
            except Exception:
                pass
        print(f"  ⚠ 无法解析 CLI 输出：{out[:200]}")
        return None


# 单元格值提取（兼容 text 数组 / {text} / 纯字符串）
def extract_text(val):
    if val is None:
        return ""
    if isinstance(val, list):
        if not val:
            return ""
        v0 = val[0]
        if isinstance(v0, dict):
            return v0.get("text") or v0.get("value") or ""
        return str(v0)
    if isinstance(val, dict):
        return val.get("text") or val.get("value") or ""
    return str(val)


def to_number(val):
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, list) and val:
        v0 = val[0]
        t = v0.get("text") if isinstance(v0, dict) else v0
        try:
            return float(t)
        except Exception:
            return 0
    try:
        return float(val)
    except Exception:
        return 0


def list_records(sheet_title, limit=1000):
    """分页拉取某子表全部记录（按 sheet_title 定位）。"""
    records = []
    cursor = None
    while True:
        payload = {"docid": DOCID, "sheet_title": sheet_title, "limit": limit}
        if cursor:
            payload["cursor"] = cursor
        data = run_cli("records list", payload)
        if not data:
            break
        if data.get("errcode", 0) != 0:
            print(f"  ⚠ 拉取「{sheet_title}」失败：{data.get('errmsg')}（可能为权限问题）")
            break
        recs = data.get("records") or []
        records.extend(recs)
        cursor = data.get("next_cursor")
        if not cursor or not recs:
            break
        if len(records) >= 5000:
            break
    return records


# ===== 1. 拉取全厂汇总 =====
print(">>> 1. 拉取全厂汇总数据...")
summary = list_records("全厂汇总")
if not summary:
    print("  ❌ 未获取到全厂汇总数据，请检查 docid / 子表名称「全厂汇总」/ CLI 授权")
    sys.exit(1)

factories = []
for rec in summary:
    v = rec.get("values") or {}
    name = extract_text(v.get("厂名"))
    if not name:
        continue
    factories.append({
        "name": name,
        "total": to_number(v.get("问题数")),
        "completed": to_number(v.get("完成数")),
        "unfinished": to_number(v.get("未完成数")),
        "eval": extract_text(v.get("状态评价")),
    })
print(f"    获取到 {len(factories)} 个工厂数据")

if not factories and summary:
    keys = list((summary[0].get("values") or {}).keys())
    print("  ⚠ 工厂数据为空，但记录已返回。首条记录字段键名：")
    print("   ", keys)
    print("    若键名是 field_id（如 fld_xxx）而非中文，说明返回按字段ID索引，需调整脚本映射。")

# ===== 2. 遍历各子表提取分类和优先级 =====
print(">>> 2. 遍历各子表提取分类和优先级分布...")
FACTORY_SHEETS = [
    "北京乳旺一厂", "北京乳旺二厂", "北京大旺一厂", "北京大旺二厂",
    "北京大旺三厂", "北京必旺厂", "北京来旺厂", "北京行政部门",
]

cat_counter = Counter()
pri_counter = Counter()
total_records = 0

for sheet_name in FACTORY_SHEETS:
    recs = list_records(sheet_name)
    if not recs:
        print(f"    ⚠ {sheet_name} 查询失败或为空，跳过")
        continue
    for rec in recs:
        total_records += 1
        vals = rec.get("values") or {}
        cat = extract_text(vals.get("问题分类"))
        if cat:
            cat_counter[cat] += 1
        pri = extract_text(vals.get("优先级"))
        if pri:
            pri_counter[pri] += 1

print(f"    共读取 {total_records} 条记录，{len(cat_counter)} 个分类，{len(pri_counter)} 个优先级")

# 排序
categories = [{"name": c, "count": n} for c, n in cat_counter.most_common()]

pri_colors = {
    "一般-不紧急": "#66bb6a",
    "一般-紧急": "#fb8c00",
    "重要-紧急": "#c62828",
    "重要-不紧急": "#f9a825"
}
priorities = [{"name": p, "count": n, "color": pri_colors.get(p, "#888")}
              for p, n in pri_counter.most_common()]

# ===== 3. 组装数据 =====
payload = {
    "data": {
        "factories": factories,
        "categories": categories,
        "priorities": priorities
    }
}

print(f"\n=== 数据摘要 ===")
total_problems = sum(f["total"] for f in factories)
total_completed = sum(f["completed"] for f in factories)
rate = round(total_completed / total_problems * 100, 1) if total_problems > 0 else 0
print(f"问题总数: {total_problems}")
print(f"已完成: {total_completed}")
print(f"综合完成率: {rate}%")
print(f"分类数: {len(categories)}")
if categories:
    print(f"Top 3: {categories[0]['name']}({categories[0]['count']}), "
          f"{categories[1]['name']}({categories[1]['count']}), "
          f"{categories[2]['name']}({categories[2]['count']})")

# ===== 4. 推送到 Cloudflare =====
print(f"\n>>> 3. 推送到 Cloudflare...")
try:
    import urllib.request

    UPDATE_URL = API_URL.rstrip('/') + '/api/update'
    req = urllib.request.Request(
        UPDATE_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {PASSWORD}'
        },
        method='POST'
    )

    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode('utf-8'))

    if result.get("success"):
        print(f"✅ 数据推送成功！")
    else:
        print(f"❌ 推送失败: {result}")
        sys.exit(1)

except Exception as e:
    print(f"❌ 推送失败: {e}")
    print("请检查：")
    print("  1. API_URL 是否正确")
    print("  2. PASSWORD 是否与 Cloudflare 环境变量一致")
    print("  3. 网络是否能访问 pages.dev 域名")
    sys.exit(1)

print(f"\n✅ 全部完成！推送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("   现在刷新网页即可看到最新数据。")
