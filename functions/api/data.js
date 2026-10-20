/**
 * GET /api/data
 * 返回北京总厂日稽核问题一览表的最新数据
 * 数据来源：企业微信智能表格（docid: s3_AG4A_waWABECNJmGuMZYOQwujgdTe）
 * 兜底数据内嵌在此，优先从 KV 读取缓存数据覆盖
 */
const DEFAULT_DATA = {
  factories: [
    { name: "北京乳旺一厂", total: 85, completed: 75, unfinished: 15, eval: "良好" },
    { name: "北京乳旺二厂", total: 280, completed: 269, unfinished: 11, eval: "优秀" },
    { name: "北京大旺一厂", total: 216, completed: 212, unfinished: 4, eval: "优秀" },
    { name: "北京大旺二厂", total: 51, completed: 51, unfinished: 0, eval: "偏低" },
    { name: "北京大旺三厂", total: 123, completed: 117, unfinished: 6, eval: "达标" },
    { name: "北京必旺厂", total: 47, completed: 34, unfinished: 14, eval: "优秀" },
    { name: "北京来旺厂", total: 57, completed: 56, unfinished: 5, eval: "优秀" },
    { name: "北京行政部门", total: 4, completed: 0, unfinished: 4, eval: "" }
  ],
  categories: [
    { name: "鼠虫害管理", count: 174 },
    { name: "制程管理", count: 151 },
    { name: "设备管理", count: 138 },
    { name: "卫生管理", count: 117 },
    { name: "异物管理", count: 107 },
    { name: "交叉污染", count: 52 },
    { name: "计量管理", count: 35 },
    { name: "化学品管理", count: 35 },
    { name: "原物料管理", count: 23 },
    { name: "标识管理", count: 14 },
    { name: "人员管理", count: 8 },
    { name: "文件记录管理", count: 6 },
    { name: "厂房建筑", count: 2 },
    { name: "食品添加剂", count: 1 }
  ],
  priorities: [
    { name: "一般-不紧急", count: 334, color: "#66bb6a" },
    { name: "一般-紧急", count: 307, color: "#fb8c00" },
    { name: "重要-紧急", count: 163, color: "#c62828" },
    { name: "重要-不紧急", count: 57, color: "#f9a825" }
  ]
};

export async function onRequest(context) {
  const { request, env } = context;
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  };

  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
  if (request.method !== 'GET') return new Response(JSON.stringify({ error: '仅支持 GET' }), { status: 405, headers });

  try {
    // 优先从 KV 读取缓存数据
    if (env && env["qa-question-kv"]) {
      const cached = await env["qa-question-kv"].get('factory_data', 'json');
      if (cached) {
        return new Response(JSON.stringify({ success: true, source: 'kv', data: cached }), { status: 200, headers });
      }
    }
    // 无缓存则返回兜底数据
    return new Response(JSON.stringify({ success: true, source: 'default', data: DEFAULT_DATA }), { status: 200, headers });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500, headers });
  }
}
