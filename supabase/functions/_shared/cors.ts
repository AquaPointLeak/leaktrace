/* The apps are static HTML files served from a different origin to the
   functions, so every response needs these headers and every function needs
   to answer the browser's preflight OPTIONS request.

   ALLOWED_ORIGIN can be set as a secret to lock this down to your own site:
     supabase secrets set ALLOWED_ORIGIN=https://yourdomain.com
   Left unset it allows any origin, which is the same exposure the anon key
   already has — the real access checks are inside each function. */

const ALLOWED_ORIGIN = Deno.env.get('ALLOWED_ORIGIN') || '*';

export const corsHeaders = {
  'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
  'Access-Control-Allow-Headers': 'authorization, content-type, apikey, x-client-info',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Vary': 'Origin'
};

export function preflight(req: Request): Response | null {
  return req.method === 'OPTIONS' ? new Response('ok', { headers: corsHeaders }) : null;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' }
  });
}
