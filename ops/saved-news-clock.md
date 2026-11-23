# Accepted news publication clock

The Monitor Supabase project already stores the restricted Brief Actions token
and dispatches the daily government import. Its additional timer invokes
`Publish Saved News Checkpoints` every 15 minutes. The work stays in GitHub.
The GitHub hourly schedule is a fallback.

Install `install-saved-news-clock.sql` in that project. The named Cron job is
updated in place when the installer is applied again. It reads the existing
`brief_github_actions_dispatch` Vault entry without exposing its value.

The repository check starts no writer, classifier, research job or model. It
publishes only accepted article versions missing from the live edition and
skips an active publisher. Checkpoint builds retain source and public-site
validation and skip translations, research enrichment and social preparation.

Check Cron job execution and the HTTP response status, then the matching GitHub
dispatch run, its check output, build, Pages deployment and live article bodies.
A dispatch response alone does not prove publication.
