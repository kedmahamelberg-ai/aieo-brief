-- Activate only after a Brief-only Actions read/write token is stored in Vault
-- as brief_github_actions_dispatch AND a no-force test dispatch returns HTTP 204.
-- Run in Supabase project jnzibjjejmfochertwco.
do $$
begin
  if not exists (
    select 1 from vault.secrets
    where name = 'brief_github_actions_dispatch'
  ) then
    raise exception 'Store and verify the Brief-scoped Actions token before activation';
  end if;
end;
$$;

-- Every-minute invocation lets the function use Europe/Amsterdam local time.
-- It sends at most one request per local day, between 16:20 and 16:25.
select cron.schedule(
  'brief-government-1620-amsterdam',
  '* * * * *',
  'select brief_scheduler.dispatch_backup();'
);
