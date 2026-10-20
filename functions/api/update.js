/**
 * POST /api/update
 * 更新北京总厂日稽核问题一览表的数据到 KV
 * 需要 Authorization: Bearer <PASSWORD> 鉴权
 */
export async function onRequest(context) {
  const { request, env } = context;
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
  };

  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
  if (request.method !== 'POST') return new Response(JSON.stringify({ error: '仅支持 POST' }), { status: 405, headers });

  // Bearer 鉴权
  const auth = request.headers.get('Authorization') || '';
  const password = env.PASSWORD || '';
  if (!auth.startsWith('Bearer ') || auth.slice(7) !== password) {
    return new Response(JSON.stringify({ error: '鉴权失败' }), { status: 403, headers });
  }

  try {
    const body = await request.json();
    if (!body.data) {
      return new Response(JSON.stringify({ error: '缺少 data 字段' }), { status: 400, headers });
    }

    if (env && env.DATA_KV) {
      await env.DATA_KV.put('factory_data', JSON.stringify(body.data));
      return new Response(JSON.stringify({ success: true, message: '数据已更新' }), { status: 200, headers });
    } else {
      return new Response(JSON.stringify({ error: 'KV 未绑定' }), { status: 500, headers });
    }
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500, headers });
  }
}
