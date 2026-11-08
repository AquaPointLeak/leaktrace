-- Applied to Supabase project zakdszzeqapdpxdyvkvd on 2026-11-08.
--
-- 1. A normal user copying an approved catalogue preset no longer sends it back to
--    "pending": increment_preset_copies() updated the row, and the guard trigger
--    treated that as a non-admin edit and reset review_state.
-- 2. Only approved presets can be counted, and owners can't set their own copy_count.
-- 3. Report numbers come from an atomic per-user counter, so two devices can't be
--    handed the same number. Numbers are never reused: a draft that is started and
--    discarded leaves a gap.
-- 4. Signed-out visitors can no longer call any of these functions.
-- 5. touch_updated_at() gets a fixed search_path (Supabase security advisor).

-- 1 + 2 -------------------------------------------------------------------
create or replace function public.guard_preset_review()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  -- Admins, and the copy counter (which sets app.copy_bump), pass through untouched.
  if public.is_admin() or current_setting('app.copy_bump', true) = '1' then
    return new;
  end if;

  -- Everyone else goes to the back of the review queue and can't set the count.
  new.review_state := 'pending';
  new.review_note  := null;
  new.reviewed_at  := null;
  new.reviewed_by  := null;
  if tg_op = 'INSERT' then
    new.copy_count := 0;
  else
    new.copy_count := old.copy_count;
  end if;
  return new;
end;
$$;

create or replace function public.increment_preset_copies(preset_id text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  perform set_config('app.copy_bump', '1', true);
  update public.public_presets
     set copy_count = copy_count + 1
   where id = preset_id
     and review_state = 'approved';
  perform set_config('app.copy_bump', '0', true);
end;
$$;

-- 3 -----------------------------------------------------------------------
create table if not exists public.report_counters (
  owner_id    uuid primary key references auth.users (id) on delete cascade,
  last_number integer not null default 0
);
alter table public.report_counters enable row level security;
revoke all on public.report_counters from anon, authenticated;   -- only next_report_number() touches it

create or replace function public.next_report_number()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  uid uuid := auth.uid();
  n   integer;
begin
  if uid is null then
    raise exception 'Not signed in';
  end if;

  insert into public.report_counters (owner_id, last_number)
  values (uid, (select coalesce(max(report_number), 0) from public.reports where owner_id = uid) + 1)
  on conflict (owner_id) do update
    set last_number = greatest(
          public.report_counters.last_number,
          (select coalesce(max(report_number), 0) from public.reports where owner_id = uid)
        ) + 1
  returning last_number into n;

  return n;
end;
$$;

-- 4 -----------------------------------------------------------------------
revoke execute on function public.increment_preset_copies(text)       from public, anon;
revoke execute on function public.is_admin()                           from public, anon;
revoke execute on function public.next_report_number()                 from public, anon;
revoke execute on function public.review_preset(text, text, text)     from public, anon;
revoke execute on function public.guard_preset_review()                from public, anon, authenticated;

grant execute on function public.increment_preset_copies(text)        to authenticated;
grant execute on function public.is_admin()                           to authenticated;
grant execute on function public.next_report_number()                 to authenticated;
grant execute on function public.review_preset(text, text, text)      to authenticated;

-- 5 -----------------------------------------------------------------------
alter function public.touch_updated_at() set search_path = public;
