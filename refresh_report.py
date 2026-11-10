#!/usr/bin/env python3
"""
北京总厂日稽核问题分析报告 - 数据刷新脚本
从智能表格拉取最新数据，推送到 Cloudflare KV

使用方法：
  1. 在 Cloudflare Pages 设置好 PASSWORD 环境变量（与 /api/update 共用）
  2. 本机通过环境变量 QA_PUSH_PASSWORD 提供推送密码，或用同目录 config.json
  3. 运行：python refresh_report.py

定时运行（Windows）：
  - 搜索"任务计划程序" → 创建基本任务
  - 触发器：每天，设置时间（如 08:00）
  - 操作：启动程序 → python refresh_report.py

定时运行（Mac/Linux）：
  crontab -e
  0 8 * * * cd /path/to/脚本目录 && python refresh_report.py
"""

import os, json, subprocess, sys
from datetime import datetime
from collections import Counter

# ============ 修改这里 ============
# 你的 Cloudflare Pages 域名
API_URL = "https://want-quality-report.pages.dev"
# 推送密码：优先读环境变量 QA_PUSH_PASSWORD，其次读同目录 config.json
# 必须与 Cloudflare 环境变量 PASSWORD 一致。前端不再持有任何密码。
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
    print("  该密码必须与 Cloudflare 环境变量 PASSWORD 一致。")
    sys.exit(1)
# ================================

SMARTSHEET_DOCID = "s3_AG4A_waWABECNJmGuMZYOQwujgdTe"

def run_cmd(cmd):
    """运行 wecom 命令并返回 JSON"""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"命令失败: {r.stderr[:300]}")
        return None
    return json.loads(r.stdout)

# ===== 1. 拉取全厂汇总数据 =====
print(">>> 1. 拉取全厂汇总数据...")
cmd = f'wecom smartsheet records list --json \'{{"docid": "{SMARTSHEET_DOCID}", "sheet_title": "全厂汇总", "limit": 999}}\''
data = run_cmd(cmd)
if not data:
    sys.exit(1)

factories = []
for rec in data.get("records", []):
    v = rec["values"]
    nm = v.get("厂名", [{}])[0].get("text", "")
    if not nm:
        continue
    factories.append({
        "name": nm,
        "total": v.get("问题数", 0),
        "completed": v.get("完成数", 0),
        "unfinished": v.get("未完成数", 0),
        "eval": v.get("状态评价", [{}])[0].get("text", "") if isinstance(v.get("状态评价"), list) else ""
    })
print(f"    获取到 {len(factories)} 个工厂数据")

# ===== 2. 遍历各子表获取分类和优先级 =====
print(">>> 2. 遍历各子表提取分类和优先级分布...")

# 各工厂子表ID
FACTORY_SHEETS = [
    ("yFaPUS", "北京乳旺一厂"),
    ("q979lj", "北京乳旺二厂"),
    ("nbZIJc", "北京大旺一厂"),
    ("fa0xYm", "北京大旺二厂"),
    ("Cgl3SL", "北京大旺三厂"),
    ("IndlEt", "北京必旺厂"),
    ("xzFaPd", "北京来旺厂"),
    ("Tf7pgo", "北京行政部门")
]

cat_counter = Counter()
pri_counter = Counter()
total_records = 0

for sheet_id, sheet_name in FACTORY_SHEETS:
    cmd = f'wecom smartsheet records list --json \'{{"docid": "{SMARTSHEET_DOCID}", "sheet_id": "{sheet_id}", "limit": 3999}}\''
    result = run_cmd(cmd)
    if not result:
        print(f"    ⚠ {sheet_name} 查询失败，跳过")
        continue

    for rec in result.get("records", []):
        total_records += 1
        vals = rec.get("values", {})

        # 问题分类
        cv = vals.get("问题分类", "")
        cat = ""
        if isinstance(cv, list) and len(cv) > 0:
            cat = cv[0].get("text", "") if isinstance(cv[0], dict) else str(cv[0])
        elif isinstance(cv, str):
            cat = cv
        if cat:
            cat_counter[cat] += 1

        # 优先级
        pv = vals.get("优先级", "")
        pri = ""
        if isinstance(pv, list) and len(pv) > 0:
            pri = pv[0].get("text", "") if isinstance(pv[0], dict) else str(pv[0])
        elif isinstance(pv, str):
            pri = pv
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
print(f"Top 3: {categories[0]['name']}({categories[0]['count']}), {categories[1]['name']}({categories[1]['count']}), {categories[2]['name']}({categories[2]['count']})")

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

print(f"\n✅ 全部完成！刷新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("   现在访问网页，点击「从智能表格刷新数据」即可看到最新数据")
