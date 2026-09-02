-- ============================================================
--  supabase-setup.sql
--
--  Run this in the Supabase dashboard: SQL Editor -> New query -> Run.
--  It is safe to run more than once (every statement is guarded).
--
--  This file covers the CUSTOMER ACCESS LINK feature only. The original
--  tables (reports, business_profile, presets, public_presets) and their
--  staff row-level-security policies were created by hand in the dashboard
--  before this file existed, so they are not reproduced here — nothing
--  below alters or weakens them.
-- ============================================================


-- ------------------------------------------------------------
--  1. Per-report access token
--
--  Each report gets a long random token. The customer's emailed link
--  carries it, and that link alone opens the report — no password and no
--  magic link. 24 random bytes is 192 bits; gen_random_uuid() would only
--  be 122 and reads like a guessable record id.
--
--  Because the column carries a DEFAULT and is NOT NULL, the apps need no
--  code to create tokens: existing rows are backfilled here, and new rows
--  get one automatically. The apps' upsert never lists this column, so an
--  ordinary save can never overwrite a token that is already in use.
-- ------------------------------------------------------------

alter table public.reports
  add column if not exists access_token text;

update public.reports
   set access_token = encode(gen_random_bytes(24), 'hex')
 where access_token is null;

alter table public.reports
  alter column access_token set default encode(gen_random_bytes(24), 'hex');

alter table public.reports
  alter column access_token set not null;

create unique index if not exists reports_access_token_key
  on public.reports (access_token);


-- ------------------------------------------------------------
--  2. Reading a report with nothing but the token
--
--  Deliberately NOT done with a row-level-security policy. A policy cannot
--  see the filter the browser asked for, so the only anonymous policy that
--  would work here is "any shared report is readable", and a visitor could
--  then simply ask for all of them. This function is the access rule
--  instead: it is the one and only way an anonymous visitor can reach a
--  report, and it hands back only the row whose token was supplied.
--
--  It returns the business profile in the same call so the letterhead and
--  logo render for a signed-out visitor without opening up
--  business_profile to anonymous reads.
--
--  shared_with_client is required, which makes the "Let this client sign
--  in and view this report" checkbox in the app a kill switch: untick it
--  and every link already sent out stops working.
-- ------------------------------------------------------------

create or replace function public.report_by_token(tok text)
returns json
language sql
security definer
set search_path = public
as $$
  select json_build_object(
           'report',    r.data,
           'business',  coalesce(b.data, '{}'::jsonb),
           'report_id', r.id
         )
    from public.reports r
    left join public.business_profile b on b.owner_id = r.owner_id
   where r.access_token = tok
     and r.shared_with_client = true
     and length(tok) >= 32
   limit 1;
$$;

revoke all on function public.report_by_token(text) from public;
grant execute on function public.report_by_token(text) to anon, authenticated;


-- ------------------------------------------------------------
--  3. Replacing a link that has gone astray
--
--  Issues the report a fresh token, which immediately breaks every copy of
--  the old link. Owner-scoped, so one account cannot rotate another's
--  report. There is no button for this in the app yet — run it here:
--
--      select public.rotate_report_token('<report id>');
--
--  NOTE: the argument type must match your reports.id column. Check with
--      select data_type from information_schema.columns
--       where table_name = 'reports' and column_name = 'id';
--  and if it comes back 'uuid', change both `rid text` and the cast below.
-- ------------------------------------------------------------

create or replace function public.rotate_report_token(rid text)
returns text
language sql
security definer
set search_path = public
as $$
  update public.reports
     set access_token = encode(gen_random_bytes(24), 'hex')
   where id::text = rid
     and owner_id = auth.uid()
  returning access_token;
$$;

revoke all on function public.rotate_report_token(text) from public;
grant execute on function public.rotate_report_token(text) to authenticated;


-- ------------------------------------------------------------
--  4. Check it worked
-- ------------------------------------------------------------

-- Every report should now show a 48-character token:
--   select id, length(access_token) from public.reports limit 5;

-- Paste a real token to confirm the reader works (returns one row, or no
-- rows if that report is not currently shared):
--   select public.report_by_token('<paste a token here>');


-- ============================================================
--  Still to do outside this file, or the Send to Customer button
--  will not work:
--
--    1. Create a Resend account and VERIFY YOUR SENDING DOMAIN.
--       An unverified domain can only mail your own address — this is
--       the most common first failure.
--
--    2. supabase secrets set RESEND_API_KEY=re_xxx \
--                            RESEND_FROM='Your Company <reports@yourdomain.com>'
--
--    3. supabase functions deploy send-report-email report-media-url
--
--    4. In the apps, set PORTAL_URL (top of the <script> block in both
--       leak-report-builder-desktop.html and -mobile.html) to wherever
--       aquapoint-portal.html is hosted.
--
--    5. In the app, open Business Settings and fill in the email subject
--       and message.
--
--  Videos additionally need the report-media-url function: anonymous
--  visitors cannot sign storage URLs themselves, and granting them access
--  to the report-media bucket directly would expose every file in it.
--  Photos are stored inside the report itself and need nothing.
-- ============================================================
