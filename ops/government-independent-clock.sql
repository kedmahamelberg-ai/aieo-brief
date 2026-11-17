-- Prepare a separate Brief backup clock in the existing Monitor scheduler project.
-- This file creates no cron job and sends no request. The token is never stored here.
create schema if not exists brief_scheduler;
revoke all on schema brief_scheduler from public, anon, authenticated;

create table if not exists brief_scheduler.dispatches (
  import_date date primary key,
  requested_at timestamptz not null default now(),
  request_id bigint not null
);
alter table brief_scheduler.dispatches enable row level security;
revoke all on brief_scheduler.dispatches from public, anon, authenticated;

create or replace function brief_scheduler.dispatch_backup()
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
  -- pg_cron checks each minute. This local-time window follows DST.
  if local_now::time < time '16:20' or local_now::time >= time '16:25' then
    return 'outside backup window';
  end if;
  perform pg_advisory_xact_lock(162020);
  if exists (
    select 1 from brief_scheduler.dispatches
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
  insert into brief_scheduler.dispatches(import_date, request_id)
    values (local_now::date, request);
  return 'backup dispatch queued';
end;
$$;
revoke all on function brief_scheduler.dispatch_backup() from public, anon, authenticated;
