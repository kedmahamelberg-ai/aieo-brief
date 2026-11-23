# Independent daily clock for Governments say

Status: the 16:20 backup is active. On 23 November, the Brief-only Vault token and `brief-government-1620-amsterdam` cron job were verified in the live project. The Morning backup is defined in `government-morning-clock.sql` and has its own daily idempotency table.

## Why this exists

The Monitor's 15:00 Europe/Amsterdam collection succeeded on both 16 and 17 November, but GitHub did not create the Brief government's scheduled 16:05 event or the later :35 retry events. The Brief's own due gate was ready. A separate Supabase pg_cron clock removes dependence on GitHub's schedule event delivery. GitHub runner queues can still delay execution.

The backups dispatch the existing main-branch `collect-government-briefs.yml` at **10:20 and 16:20 Europe/Amsterdam**. They set `force_refresh=false`; they do not collect Monitor sources or run an editorial model. The import compares the current Monitor feed to saved fingerprints, so a changed morning item is imported even if the preceding afternoon ran. The workflow's `brief-government-announcements` concurrency group serializes overlapping wakeups. Each external clock sends at most one request per Amsterdam date. GitHub's own scheduled checks remain in place.

## Morning activation

The owner already stored the Brief-only Actions read/write token in Supabase Vault as `brief_github_actions_dispatch`; the 16:20 clock uses it. Do not copy the token into repository files, SQL text, logs, or browser URLs.

Apply `government-morning-clock.sql` in project `jnzibjjejmfochertwco`. It requires the existing token and active afternoon clock, creates a separate private morning idempotency table, and registers `brief-government-1020-amsterdam`. The local-time window follows daylight saving. Calling `brief_scheduler.dispatch_morning()` outside 10:20–10:25 returns `outside morning backup window` without dispatching.

After the next 10:20 Amsterdam slot, verify the new dispatch row, GitHub API HTTP 204 while the response record is retained, the corresponding `workflow_dispatch` run, saved `last_checked_at`, and the live Brief feed. An enqueued HTTP request alone does not prove import or publication.

The existing `monitor_github_actions_dispatch` token expires on **10 February 2027**, according to GitHub's authenticated `github-authentication-token-expiration` response header checked on 17 November 2026. The Brief backups use their own token and do not alter the Monitor collectors or clocks.

## Inspection

```sql
select jobid, jobname, schedule, active from cron.job
where jobname in ('brief-government-1020-amsterdam', 'brief-government-1620-amsterdam');

select d.import_date, d.requested_at, r.status_code, r.timed_out, r.error_msg
from brief_scheduler.dispatches d
left join net._http_response r on r.id = d.request_id
order by d.import_date desc limit 7;

select d.import_date, d.requested_at, r.status_code, r.timed_out, r.error_msg
from brief_scheduler.morning_dispatches d
left join net._http_response r on r.id = d.request_id
order by d.import_date desc limit 7;
```

The `net._http_response` rows are transient. Inspect GitHub runs and the saved feed before any retry. Do not blindly dispatch a second run.

To disable a backup, use `cron.alter_job(job_id := <verified job id>, active := false)`. Do not edit `cron.job` directly. The Brief's GitHub cron and saved-date gate remain in place.
