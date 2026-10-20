/**
 * GET /api/data
 * 返回北京总厂日稽核问题一览表的最新数据
 * 数据来源：企业微信智能表格（docid: s3_AG4A_waWABECNJmGuMZYOQwujgdTe）
 * 兜底数据内嵌在此，优先从 KV 读取缓存数据覆盖
 */
const DEFAULT_DATA = {
  factories: [
    { name: "北京乳旺一厂", total: 82, completed: 90, unfinished: 155, rate: 286.0, eval: "良好" },
    { name: "北京乳旺二厂", total: 224, completed: 161, unfinished: 225, rate: 349.0, eval: "优秀" },
    { name: "北京大旺一厂", total: 145, completed: 193, unfinished: 232, rate: 369.0, eval: "优秀" },
    { name: "北京大旺二厂", total: 25, completed: 135, unfinished: 273, rate: 335.0, eval: "偏低" },
    { name: "北京大旺三厂", total: 86, completed: 167, unfinished: 233, rate: 374.0, eval: "达标" },
    { name: "北京必旺厂", total: 31, completed: 177, unfinished: 201, rate: 364.0, eval: "优秀" },
    { name: "北京来旺厂", total: 99, completed: 206, unfinished: 216, rate: 378.0, eval: "优秀" },
    { name: "北京行政部门", total: 268, completed: 259, unfinished: 189, rate: 388.0, eval: "--" }
  ],
  categories: [
    { name: "鼠虫害管理", count: 174 },
    { name: "制程管理", count: 150 },
    { name: "设备管理", count: 138 },
    { name: "卫生管理", count: 107 },
    { name: "异物管理", count: 97 },
    { name: "交叉污染", count: 49 },
    { name: "计量管理", count: 35 },
    { name: "化学品管理", count: 33 },
    { name: "原物料管理", count: 22 },
    { name: "标识管理", count: 44 },
    { name: "人员管理", count: 38 },
    { name: "文件记录管理", count: 106 },
    { name: "厂房建筑", count: 27 },
    { name: "食品添加剂", count: 21 }
  ],
  priorities: [
    { name: "一般-不紧急", count: 333, color: "#66bb6a" },
    { name: "一般-紧急", count: 306, color: "#fb8c00" },
    { name: "重要-紧急", count: 170, color: "#c62828" },
    { name: "重要-不紧急", count: 757, color: "#f9a825" }
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
    if (env && env.DATA_KV) {
      const cached = await env.DATA_KV.get('factory_data', 'json');
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
