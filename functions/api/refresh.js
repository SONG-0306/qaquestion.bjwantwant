/**
 * POST /api/refresh
 * 从企业微信智能表格实时拉取最新数据，写入 KV 缓存并返回给前端
 *
 * 触发：同源 POST /api/refresh（由页面按钮发起，无需客户端密码）
 *
 * 安全说明：
 *   前端不持有任何密钥，真正的企微凭证（WECOM_CORPID / WECOM_AGENT_SECRET）
 *   仅存在于 Cloudflare 服务端环境变量。本接口通过同源校验防止外部站点滥用企微接口。
 *   如需更强防护，可在 Cloudflare 侧为站点开启 Access。
 *
 * 需要在 Cloudflare 环境变量中配置：
 *   WECOM_CORPID        - 企业ID（CorpID）
 *   WECOM_AGENT_SECRET  - 自建应用的凭证密钥
 *
 * KV 绑定 Variable name：qa-question-kv
 *
 * 接口依据企业微信开发者中心文档（2026-11-10）：
 *   查询子表  /document/53109  -> POST /cgi-bin/wedoc/smartsheet/get_sheet
 *   查询记录  /document/53121  -> POST /cgi-bin/wedoc/smartsheet/get_records
 *   记录值以字段名作为 key 需传 key_type=CELL_VALUE_KEY_TYPE_FIELD_TITLE
 */

const DOCID = 's3_AG4A_waWABECNJmGuMZYOQwujgdTe';
const WECOM_BASE = 'https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet';

// 各工厂子表的 sheet_id（从智能表格基本信息获取）
const FACTORY_SHEETS = {
  'yFaPUS': '北京乳旺一厂',
  'q979lj': '北京乳旺二厂',
  'nbZIJc': '北京大旺一厂',
  'fa0xYm': '北京大旺二厂',
  'Cgl3SL': '北京大旺三厂',
  'IndlEt': '北京必旺厂',
  'xzFaPd': '北京来旺厂',
  'Tf7pgo': '北京行政部门'
};

export async function onRequest(context) {
  const { request, env } = context;
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Cache-Control': 'no-store'
  };

  // OPTIONS 预检
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
  if (request.method !== 'POST') {
    return new Response(JSON.stringify({ error: '仅支持 POST' }), { status: 405, headers });
  }

  // 同源校验：仅允许本站页面触发，避免外部滥用企微接口
  if (!isSameOrigin(request)) {
    return new Response(JSON.stringify({ success: false, error: '仅允许同源请求' }), { status: 403, headers });
  }

  try {
    const corpid = env.WECOM_CORPID;
    const secret = env.WECOM_AGENT_SECRET;
    if (!corpid || !secret) {
      throw new Error('请在 Cloudflare 环境变量中配置 WECOM_CORPID 和 WECOM_AGENT_SECRET');
    }

    // 获取 access_token
    const tokenResp = await fetch(
      `https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=${encodeURIComponent(corpid)}&corpsecret=${encodeURIComponent(secret)}`,
      { headers: { 'Content-Type': 'application/json' } }
    );
    const tokenData = await tokenResp.json();
    if (tokenData.errcode !== 0) {
      throw new Error(`获取 access_token 失败: ${tokenData.errmsg}`);
    }
    const accessToken = tokenData.access_token;

    // 解析「全厂汇总」子表 sheet_id
    const summarySheetId = await getSheetIdByTitle(accessToken, '全厂汇总');
    if (!summarySheetId) {
      throw new Error('未找到名为「全厂汇总」的子表，请确认智能表格中存在该子表');
    }

    // 查询全厂汇总
    const summaryData = await getRecords(accessToken, summarySheetId);
    if (summaryData.errcode !== 0) {
      throw new Error(`查询全厂汇总失败: ${summaryData.errmsg}`);
    }

    // 组装工厂数据
    const factories = [];
    for (const record of summaryData.records || []) {
      const v = record.values || {};
      const name = extractText(v['厂名']);
      if (!name) continue;
      factories.push({
        name,
        total: toNumber(v['问题数']),
        completed: toNumber(v['完成数']),
        unfinished: toNumber(v['未完成数']),
        eval: extractText(v['状态评价'])
      });
    }

    // 遍历各工厂子表获取分类和优先级分布
    const catMap = {};
    const priMap = {};

    for (const [sheetId, sheetName] of Object.entries(FACTORY_SHEETS)) {
      try {
        const sheetData = await getRecords(accessToken, sheetId);
        if (sheetData.errcode !== 0) {
          console.error(`查询 ${sheetName} 失败:`, sheetData.errmsg);
          continue;
        }
        for (const record of sheetData.records || []) {
          const vals = record.values || {};

          const cat = extractText(vals['问题分类']);
          if (cat) catMap[cat] = (catMap[cat] || 0) + 1;

          const pri = extractText(vals['优先级']);
          if (pri) priMap[pri] = (priMap[pri] || 0) + 1;
        }
      } catch (e) {
        console.error(`查询 ${sheetName} 异常:`, e.message);
      }
    }

    // 排序
    const categories = Object.entries(catMap)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));

    const priColors = {
      '一般-不紧急': '#66bb6a',
      '一般-紧急': '#fb8c00',
      '重要-紧急': '#c62828',
      '重要-不紧急': '#f9a825'
    };
    const priorities = Object.entries(priMap)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count, color: priColors[name] || '#888' }));

    // 组装最终数据
    const resultData = { factories, categories, priorities };

    // 写入 KV 缓存
    if (env["qa-question-kv"]) {
      await env["qa-question-kv"].put('factory_data', JSON.stringify(resultData));
    }

    // 返回给前端
    return new Response(JSON.stringify({
      success: true,
      source: '智能表格（实时）',
      updatedAt: new Date().toISOString(),
      data: resultData
    }), { status: 200, headers });

  } catch (err) {
    return new Response(JSON.stringify({
      success: false,
      error: err.message
    }), { status: 500, headers });
  }
}

// 通过子表名称解析 sheet_id
async function getSheetIdByTitle(accessToken, title) {
  const resp = await fetch(`${WECOM_BASE}/get_sheet?access_token=${accessToken}`, {
    method: 'POST',
    body: JSON.stringify({ docid: DOCID, need_all_type_sheet: true }),
    headers: { 'Content-Type': 'application/json' }
  });
  const data = await resp.json();
  if (data.errcode !== 0) {
    throw new Error(`查询子表失败: ${data.errmsg}`);
  }
  const list = data.sheet_list || [];
  const found = list.find(s => s.title === title && s.type === 'smartsheet');
  return found ? found.sheet_id : null;
}

// 查询子表记录（按字段名返回）
async function getRecords(accessToken, sheetId) {
  const resp = await fetch(`${WECOM_BASE}/get_records?access_token=${accessToken}`, {
    method: 'POST',
    body: JSON.stringify({
      docid: DOCID,
      sheet_id: sheetId,
      limit: 1000,
      key_type: 'CELL_VALUE_KEY_TYPE_FIELD_TITLE'
    }),
    headers: { 'Content-Type': 'application/json' }
  });
  return resp.json();
}

// 从单元格值中提取文本（支持 [{text}] 数组、字符串、{text} 对象）
function extractText(val) {
  if (Array.isArray(val) && val.length > 0) {
    return typeof val[0] === 'object' ? (val[0].text || '') : String(val[0]);
  }
  if (typeof val === 'string') return val;
  if (val && typeof val === 'object' && val.text) return val.text;
  return '';
}

// 单元格数值提取（数字字段直接返回数字）
function toNumber(val) {
  if (typeof val === 'number') return val;
  if (Array.isArray(val) && val.length > 0) {
    const n = typeof val[0] === 'object' ? val[0].text : val[0];
    return Number(n) || 0;
  }
  return Number(val) || 0;
}

// 同源校验：比较请求来源 host 与当前 host 是否一致
function isSameOrigin(request) {
  const host = new URL(request.url).host;
  const origin = request.headers.get('Origin');
  const referer = request.headers.get('Referer');
  const refHost = origin ? safeHost(origin) : (referer ? safeHost(referer) : null);
  if (!refHost) return true; // 本地/无头测试（无 Origin/Referer）放行
  return refHost === host;
}

function safeHost(v) {
  try { return new URL(v).host; } catch { return null; }
}
