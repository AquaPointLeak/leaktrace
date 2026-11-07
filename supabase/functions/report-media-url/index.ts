/* Signs a video URL for a customer who arrived on an access link and has no
   account.

   Anonymous visitors cannot sign storage URLs themselves, and the only way
   to let them would be to open the whole report-media bucket to the anon
   role — which would expose every customer's footage to everyone. So this
   function does the signing, and only after checking that the file being
   asked for actually belongs to the report whose token was presented.

   That membership check is the entire point of the function. Without it
   this would be an open signer for the bucket.

   Photos need none of this: they live inside the report record itself.

   Deploy: supabase functions deploy report-media-url  (verify_jwt = false) */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { preflight, json } from '../_shared/cors.ts';

const SUPABASE_URL     = Deno.env.get('SUPABASE_URL')!;
const SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const MEDIA_BUCKET     = 'report-media';
const URL_TTL_SECONDS  = 3600;

/* Every storage path the report refers to, wherever it sits in the tree. */
function mediaPaths(report: Record<string, unknown>): Set<string> {
  const paths = new Set<string>();
  const collect = (photos: unknown) => {
    for (const m of (photos as Array<Record<string, string>>) || []) {
      if (m?.path) paths.add(m.path);
    }
  };
  for (const cat of (report?.categories as Array<Record<string, unknown>>) || []) {
    collect(cat?.photos);
    for (const item of (cat?.items as Array<Record<string, unknown>>) || []) collect(item?.photos);
  }
  return paths;
}

Deno.serve(async (req: Request) => {
  const pre = preflight(req);
  if (pre) return pre;

  if (req.method !== 'POST') return json({ error: 'POST only' }, 405);

  try {
    const body  = await req.json().catch(() => null);
    const token = String(body?.token || '');
    const path  = String(body?.path || '');

    /* One message for every failure below. Telling the caller which part
       was wrong would turn this into a way to test guessed tokens. */
    const denied = () => json({ error: 'That video is not available.' }, 404);

    if (token.length < 32 || !path) return denied();

    const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

    const { data: report, error } = await admin
      .from('reports')
      .select('id, data, shared_with_client')
      .eq('access_token', token)
      .maybeSingle();

    if (error || !report || !report.shared_with_client) return denied();
    if (!mediaPaths((report.data as Record<string, unknown>) || {}).has(path)) return denied();

    const { data: signed, error: signErr } = await admin
      .storage
      .from(MEDIA_BUCKET)
      .createSignedUrl(path, URL_TTL_SECONDS);

    if (signErr || !signed?.signedUrl) {
      console.error('signing failed for report', report.id);
      return denied();
    }

    return json({ url: signed.signedUrl });

  } catch (err) {
    console.error('report-media-url failed', (err as Error)?.message);
    return json({ error: 'That video is not available.' }, 404);
  }
});
