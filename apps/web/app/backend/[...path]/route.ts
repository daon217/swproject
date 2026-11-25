const base = process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000';
async function proxy(req: Request) {
  const url=new URL(req.url);
  const path=url.pathname.slice('/backend'.length);
  if (!/^\/v2\/(auth\/(login|logout|signup)|admin\/[a-z0-9/\-]+|offers)$/.test(path))
    return new Response(null,{status:404});
  const body=['GET','HEAD'].includes(req.method)?undefined:await req.arrayBuffer();
  if(body && body.byteLength>65536)return new Response(null,{status:413});
  const headers=new Headers({'Content-Type':'application/json'});
  if(req.headers.has('authorization'))headers.set('Authorization',req.headers.get('authorization')!);
  try {
    const result=await fetch(base+path+url.search,{method:req.method,headers,body,
      cache:'no-store',redirect:'manual',signal:AbortSignal.timeout(10000)});
    return new Response(result.body,{status:result.status,headers:{
      'Content-Type':result.headers.get('content-type') || 'application/json', 'Cache-Control':'no-store'}});
  } catch { return Response.json({error:{code:'BACKEND_UNAVAILABLE'}},{status:502}); }
}
export const GET=proxy, POST=proxy, PUT=proxy, PATCH=proxy, DELETE=proxy;
