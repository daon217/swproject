export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const response = await fetch(`${process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000'}/v2/offers?selected_domain=product`, {cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('unavailable');
    return Response.json(await response.json());
  } catch {
    return Response.json({error:'API_UNAVAILABLE'}, {status:503});
  }
}
