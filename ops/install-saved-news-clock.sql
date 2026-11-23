-- Run once in the Monitor Supabase project, which already owns the Brief
-- dispatch token and the government delivery clocks. No schema changes.
-- The token value remains in Vault and must never be copied into this file.
do $check$
begin
  if not exists (
    select 1 from vault.decrypted_secrets
    where name = 'brief_github_actions_dispatch' and length(decrypted_secret) > 0
  ) then
    raise exception 'The existing Brief Actions dispatch token is missing';
  end if;
end
$check$;

select cron.schedule(
  'brief-saved-news-publication',
  '7,22,37,52 * * * *',
  $dispatch$
  select net.http_post(
    url := 'https://api.github.com/repos/kedmahamelberg-ai/aieo-brief/actions/workflows/publish-saved-news.yml/dispatches',
    headers := jsonb_build_object(
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || decrypted_secret,
      'X-GitHub-Api-Version', '2022-11-28'
    ),
    body := '{"ref":"main"}'::jsonb,
    timeout_milliseconds := 10000
  )
  from vault.decrypted_secrets
  where name = 'brief_github_actions_dispatch';
  $dispatch$
);

-- Verification: inspect the job metadata and HTTP status, never credentials.
select jobname, schedule, active
from cron.job where jobname = 'brief-saved-news-publication';

-- To stop this timer: select cron.unschedule('brief-saved-news-publication');
