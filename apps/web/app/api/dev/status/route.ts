export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const response = await fetch(`${process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000'}/health`, {cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('unavailable');
    return Response.json({web:'ok', api:await response.json(), mode:'development'});
  } catch {
    return Response.json({web:'ok', api:{status:'unavailable'}}, {status:503});
  }
}
