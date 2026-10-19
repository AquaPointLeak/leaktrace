/* Emails a customer their report: the access link, the message the business
   wrote in Business Settings, the letterhead logo, and the PDF attached.

   Called from the report builder's "Send to Customer" button.

   The browser sends only the report id and the rendered message. Who the
   email goes to, what the link contains, and which logo is attached are all
   read from the database here. That is deliberate: it means this function
   can never be talked into mailing an arbitrary address, even by someone
   holding a stolen staff token — the only addresses it will ever send to
   are the ones already written on a report that the caller owns.

   Deploy:  supabase functions deploy send-report-email
   Secrets: RESEND_API_KEY, RESEND_FROM, PORTAL_URL  (and optionally ALLOWED_ORIGIN) */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';
import { corsHeaders, preflight, json } from '../_shared/cors.ts';

const SUPABASE_URL      = Deno.env.get('SUPABASE_URL')!;
const ANON_KEY          = Deno.env.get('SUPABASE_ANON_KEY')!;
const SERVICE_ROLE_KEY  = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const RESEND_API_KEY    = Deno.env.get('RESEND_API_KEY');
const RESEND_FROM       = Deno.env.get('RESEND_FROM');
const PORTAL_URL        = Deno.env.get('PORTAL_URL');

/* Resend's ceiling is 40MB for the whole message; base64 adds a third on top
   of the raw bytes. Stopping at 20MB of encoded PDF leaves room for the logo
   and the headers, and gives the sender a clear message instead of a
   provider error they cannot act on. */
const MAX_PDF_BASE64 = 20 * 1024 * 1024;
const MAX_HTML       = 200 * 1024;

/* Same rule the apps use: one field can hold several addresses. */
function reportEmails(report: Record<string, unknown>): string[] {
  const fields = (report?.customerFields as Array<Record<string, string>>) || [];
  const field  = fields.find(f => f?.role === 'email');
  const seen   = new Set<string>();
  return String(field?.value || '')
    .split(/[,;]+/)
    .map(e => e.trim())
    .filter(e => {
      if (!e || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)) return false;
      const key = e.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

/* Data URL in, bare base64 plus a filename out. */
function splitDataUrl(dataUrl: string): { content: string; filename: string } | null {
  if (typeof dataUrl !== 'string') return null;
  const at = dataUrl.indexOf('base64,');
  if (at < 0) return null;
  const content = dataUrl.slice(at + 7);
  if (!content) return null;
  const mime = /^data:([^;,]+)/.exec(dataUrl)?.[1] || 'image/png';
  const ext  = mime.split('/')[1]?.replace(/[^a-z0-9]/gi, '') || 'png';
  return { content, filename: 'logo.' + ext };
}

Deno.serve(async (req: Request) => {
  const pre = preflight(req);
  if (pre) return pre;

  if (req.method !== 'POST') return json({ error: 'POST only' }, 405);
  if (!RESEND_API_KEY || !RESEND_FROM) {
    return json({ error: 'Email is not configured yet — set RESEND_API_KEY and RESEND_FROM.' }, 500);
  }

  try {
    /* --- who is asking ---------------------------------------------------
       The project's anon key is itself a valid JWT, so the gateway's
       verify_jwt check is not enough on its own: it would let anyone with
       the (public) key through. Resolve the token to an actual user. */
    const authHeader = req.headers.get('Authorization') || '';
    const jwt = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';
    if (!jwt) return json({ error: 'Sign in first.' }, 401);

    const { data: userData, error: userErr } =
      await createClient(SUPABASE_URL, ANON_KEY).auth.getUser(jwt);
    const user = userData?.user;
    if (userErr || !user || user.role === 'anon') return json({ error: 'Sign in first.' }, 401);

    const body = await req.json().catch(() => null);
    if (!body?.reportId) return json({ error: 'Missing report id.' }, 400);

    const subject   = String(body.subject || '').slice(0, 300).trim();
    const html      = String(body.html || '');
    const pdfBase64 = String(body.pdfBase64 || '');
    const filename  = String(body.filename || 'report.pdf').replace(/[^\w.\-]/g, '_');

    if (!subject)                       return json({ error: 'The email needs a subject.' }, 400);
    if (html.length > MAX_HTML)         return json({ error: 'That message is too long to send.' }, 400);
    if (pdfBase64.length > MAX_PDF_BASE64) {
      return json({ error: 'This report is too large to email. Remove a few photos and try again.' }, 413);
    }

    /* --- is it theirs, and is it shared --------------------------------- */
    const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

    const { data: report, error: repErr } = await admin
      .from('reports')
      .select('id, owner_id, data, access_token, shared_with_client')
      .eq('id', body.reportId)
      .single();

    if (repErr || !report)             return json({ error: 'That report could not be found.' }, 404);
    if (report.owner_id !== user.id)   return json({ error: 'That report belongs to another account.' }, 403);
    if (!report.shared_with_client) {
      return json({ error: 'Turn on "Let this client sign in and view this report" first.' }, 400);
    }
    if (!report.access_token) {
      return json({ error: 'This report has no access link yet — run supabase-setup.sql.' }, 500);
    }

    /* --- who it goes to (never taken from the request) ------------------- */
    const recipients = reportEmails(report.data || {});
    if (!recipients.length) return json({ error: 'This report has no client email address on it.' }, 400);

    /* --- letterhead ------------------------------------------------------ */
    const { data: profile } = await admin
      .from('business_profile')
      .select('data')
      .eq('owner_id', report.owner_id)
      .maybeSingle();
    const biz  = (profile?.data as Record<string, string>) || {};
    const logo = splitDataUrl(biz.logoDataUrl || '');

    /* The link is built here rather than trusted from the browser, so the
       email can only ever point at this report. */
    const portalBase = String(body.portalUrl || PORTAL_URL || '').trim();
    if (!portalBase) {
      return json({ error: 'No portal address set. Add it in Business Settings.' }, 400);
    }
    const link = portalBase.split('#')[0] + '#t=' + report.access_token;

    const attachments: Array<Record<string, string>> = [
      ...(pdfBase64 ? [{ filename, content: pdfBase64 }] : [])
    ];
    /* Referenced as <img src="cid:logo"> in the HTML. Inline attachments
       survive the image blocking that kills data: URLs in most mail clients. */
    if (logo) attachments.push({ ...logo, content_id: 'logo' });

    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        from: RESEND_FROM,
        to: recipients,
        reply_to: biz.companyEmail || undefined,
        subject,
        html: html.replace(/\{\{link\}\}/g, link),
        attachments: attachments.length ? attachments : undefined
      })
    });

    if (!res.ok) {
      const detail = await res.text();
      /* The report link and the PDF are in the request body, and function
         logs are readable from the dashboard, so log neither. */
      console.error('resend rejected', report.id, res.status);
      let message = 'The email service rejected the message.';
      try { message = JSON.parse(detail)?.message || message; } catch { /* keep the default */ }
      return json({ error: message }, 502);
    }

    console.log('sent', report.id, recipients.length, 'recipient(s)');
    return json({ ok: true, sent: recipients.length });

  } catch (err) {
    console.error('send-report-email failed', (err as Error)?.message);
    return json({ error: 'Could not send the email — please try again.' }, 500);
  }
});
