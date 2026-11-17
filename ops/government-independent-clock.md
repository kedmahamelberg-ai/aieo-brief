# Independent daily clock for Governments say

Status: prepared, **not activated**. The SQL is inert until the separate activation script is run. On 17 November 2026, the existing Monitor scheduler credential could read the Brief workflow (HTTP 200) but a no-force dispatch returned HTTP 403, with GitHub requiring `actions=write`. It must not be reused or broadened silently.

## Why this exists

The Monitor's 15:00 Europe/Amsterdam collection succeeded on both 16 and 17 November, but GitHub did not create the Brief government's scheduled 16:05 event or the later :35 retry events. The Brief's own due gate was ready. A separate Supabase pg_cron clock removes dependence on GitHub's schedule event delivery. GitHub runner queues can still delay execution.

The backup dispatches the existing main-branch `collect-government-briefs.yml` at **16:20 Europe/Amsterdam**. It sets `force_refresh=false`; it does not collect Monitor sources or run an editorial model. The existing `government_brief_schedule.py` saved-date guard skips a second import after one already ran. The workflow's `brief-government-announcements` concurrency group serializes overlapping wakeups. The external clock sends at most one request per Amsterdam date. It intentionally leaves GitHub's cron entries as the primary trigger.

## Activation after owner approval

1. Create a new fine-grained GitHub token with access only to `kedmahamelberg-ai/aieo-brief` and **Actions: Read and write**. No Contents write permission is needed. Set an expiry and renewal reminder. Creating this token or adding Brief access to an existing token expands security-sensitive access and requires owner approval.
2. Store the token in Supabase Vault in project `jnzibjjejmfochertwco` as `brief_github_actions_dispatch`. Never put it in repository files, SQL text, logs, or browser URLs.
3. Apply `government-independent-clock.sql` in that project. It creates a private schema, a private idempotency table, and the dispatch function, but no cron job.
4. Test a no-force dispatch using the Vault secret. Require GitHub API **HTTP 204** and a corresponding workflow run. If today's import already happened, the due gate must skip collection and publication. Check that no second import occurred.
5. Apply `government-independent-clock-activate.sql`. Verify the named cron job is active. After the next 16:20 Amsterdam slot, check `brief_scheduler.dispatches`, the matching `net._http_response` status, the GitHub workflow run, saved `last_checked_at`, and the live deployed feed. An enqueued HTTP request alone is not proof of a successful import.

The existing `monitor_github_actions_dispatch` token expires on **10 February 2027**, according to GitHub's authenticated `github-authentication-token-expiration` response header checked on 17 November 2026. This Brief backup uses its own token and does not alter the Monitor collectors or clocks.

## Inspection

```sql
select jobid, jobname, schedule, active from cron.job
where jobname = 'brief-government-1620-amsterdam';

select d.import_date, d.requested_at, r.status_code, r.timed_out, r.error_msg
from brief_scheduler.dispatches d
left join net._http_response r on r.id = d.request_id
order by d.import_date desc limit 7;
```

The `net._http_response` rows are transient. Inspect GitHub runs and the saved feed before any retry. Do not blindly dispatch a second run.

To disable the backup, use `cron.alter_job(job_id := <verified job id>, active := false)`. Do not edit `cron.job` directly. The Brief's GitHub cron and saved-date gate remain in place.
