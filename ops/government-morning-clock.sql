-- Independent 10:20 Europe/Amsterdam backup for the existing Brief import.
-- Uses the Brief-only Actions token already stored in Supabase Vault.
-- The 16:20 backup and its idempotency table remain unchanged.
create schema if not exists brief_scheduler;
revoke all on schema brief_scheduler from public, anon, authenticated;

create table if not exists brief_scheduler.morning_dispatches (
  import_date date primary key,
  requested_at timestamptz not null default now(),
  request_id bigint not null
);
alter table brief_scheduler.morning_dispatches enable row level security;
revoke all on brief_scheduler.morning_dispatches from public, anon, authenticated;

create or replace function brief_scheduler.dispatch_morning()
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  local_now timestamp := clock_timestamp() at time zone 'Europe/Amsterdam';
  token text;
  request bigint;
begin
  if local_now::time < time '10:20' or local_now::time >= time '10:25' then
    return 'outside morning backup window';
  end if;
  perform pg_advisory_xact_lock(102020);
  if exists (
    select 1 from brief_scheduler.morning_dispatches
    where import_date = local_now::date
  ) then
    return 'already dispatched';
  end if;
  select decrypted_secret into token from vault.decrypted_secrets
    where name = 'brief_github_actions_dispatch';
  if token is null or token = '' then
    raise exception 'Brief scheduler credential is missing';
  end if;
  select net.http_post(
    url := 'https://api.github.com/repos/kedmahamelberg-ai/aieo-brief/actions/workflows/collect-government-briefs.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28'
    ),
    body := jsonb_build_object(
      'ref', 'main',
      'inputs', jsonb_build_object('force_refresh', 'false')
    ),
    timeout_milliseconds := 10000
  ) into request;
  insert into brief_scheduler.morning_dispatches(import_date, request_id)
    values (local_now::date, request);
  return 'morning backup dispatch queued';
end;
$$;
revoke all on function brief_scheduler.dispatch_morning() from public, anon, authenticated;

do $$
begin
  if not exists (select 1 from vault.secrets where name = 'brief_github_actions_dispatch') then
    raise exception 'Brief-only Actions token is missing from Vault';
  end if;
  if not exists (select 1 from cron.job where jobname = 'brief-government-1620-amsterdam' and active) then
    raise exception 'Existing 16:20 Brief backup clock is not active';
  end if;
end;
$$;

select cron.schedule(
  'brief-government-1020-amsterdam',
  '* * * * *',
  'select brief_scheduler.dispatch_morning();'
)
where not exists (
  select 1 from cron.job where jobname = 'brief-government-1020-amsterdam'
);
