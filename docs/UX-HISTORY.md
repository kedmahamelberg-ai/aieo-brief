# Private UX history and research use

## Deployment state

Supabase migration `brief_ux_history_v1` was applied successfully on 9 September 2026 to project `tricsbvxamjzfeckivhz`. The migration is recorded in Supabase's migration history. No previous user activity was invented or backfilled. At inspection, the detailed event and consent tables had zero rows. The website code in this patch is still to be deployed by its owner; database installation alone cannot collect browsing events.

This is a consent-based measurement implementation, not legal advice, blanket ethical approval, or a guarantee of complete telemetry. Before formal participant research or experiments, review the specific protocol, consent, age handling and retention with the relevant research institution. Do not treat product-analytics permission, newsletter consent or sign-in as research permission.

## Storage

- `brief_behavior_events`: one row per accepted event, with received and client timestamps, event UUID, pseudonymous browser identifier, session UUID, page/item key, event type, viewport bucket, consent reference, schema version, properties and a retention deadline.
- `brief_consent_receipts`: versioned independent analytics/research choices; the research choice includes an adult affirmation. Historical activity is never retroactively opted in.
- `brief_ux_tokens`: hashed private permission-management tokens, revocation and expiry. Raw tokens remain in the browser and never go to Google Analytics.
- `brief_ux_content_versions`: the public English content snapshot and its SHA-256 fingerprint. Events record content and layout versions, so changed wording can be distinguished from changed reader behavior.
- `brief_ux_research_events`: private research-only view. It excludes non-research events, expired data and linked events whose research eligibility was withdrawn.

Raw history and consent records cannot be selected directly by anonymous or signed-in readers. Controlled RPCs accept bounded, allowlisted event batches. Raw tables retain row-level security. A visitor can request removal of their own browser-linked history using their private token. The existing public aggregate counters and account likes/comments/saves remain separate.

## Event definitions and limits

`page_view` is a consented page visit, not a verified individual. `item_impression` is an item card that is at least half visible for roughly one second; it can include its displayed position and visible public counts. `story_open` is a clicked internal story link. The client captures likes/unlikes, saves/unsaves, submitted/deleted comments, sharing choices, source clicks, filters, sorts, search length/result counts, additional-story requests, manual carousel controls, notification preference changes, authentication outcomes and media controls where the relevant UI action is available.

`active_reading` records cumulative visible reading seconds while there has been user activity within the last minute. `scroll_depth` records thresholds 25/50/75/100 percent. `qualified_read` requires at least 20 active seconds and half of the article reached. These are operational measures, not proof that text was understood. Deduplicate cumulative samples when calculating time.

Raw search words, email addresses, comment bodies, exact IP addresses, user-agent strings and full URLs are not included in this UX stream. Aggregate visible card counters can be absent if they have not loaded. Advertising placement visibility is only a first-party observation; it is not a Google billable impression or an ad click. Cross-origin ad-iframe clicks and completed purchases are not inferred.

Delivery is best-effort: blockers, network errors, closed tabs and disabled measurement cause missing observations. Batches retry using the same UUIDs to prevent duplicates. A batch has at most 25 events and 32 KiB; the server limits a browser identifier to 300 accepted events per ten minutes. Anonymous token issuance and the public endpoints still need monitoring for abuse. This is not a substitute for gateway-level bot protection at scale.

## Consent and retention

Neither analytics nor research is selected automatically. Research can be enabled without Google Analytics. Product-measurement history is retained for up to 13 months; separately consented adult research history for up to 24 months. Scheduled maintenance removes expired history. Consent evidence can remain up to 30 months. These are implementation choices, not legally mandated durations.

Research withdrawal removes prior linked events from the research view and shortens product-only retention. Declining both choices removes the linked private UX history. The privacy dialog also provides explicit erasure. Public aggregate counts, functional account records and provider security logs are distinct. Clearing browser storage can remove the token needed to identify earlier browser-linked history.

## Research interpretation

An association between displayed view counts and subsequent engagement is not, by itself, a causal bandwagon effect. Position, prior popularity, content and returning-reader selection can jointly explain that association. Use recorded exposure/count snapshots and content versions for descriptive or predictive analyses; a causal test would require a separately designed, reviewed experiment. Do not manufacture counts or silently start an experiment.

## Read-only checks in the Supabase SQL Editor

```sql
select event_name, count(*) as recorded_events,
       count(*) filter(where research_eligible) as research_eligible_events
from public.brief_behavior_events
where event_schema_version='brief-ux-v1'
group by event_name order by recorded_events desc;

select count(*) as research_view_rows from public.brief_ux_research_events;
select count(*) as content_versions from public.brief_ux_content_versions;
```

An empty result before deployment or before anyone opts in is expected. A green publication workflow alone is not proof of event collection. After deployment, make a voluntary measurement choice, open a story, scroll and wait at least ten seconds; then inspect this query. Do not add synthetic production events to make the counters look active.

## Backend interface

`brief_ux_consent(p_analytics boolean, p_research boolean, p_token text)` returns the new or existing token and choices. `brief_ux_record(p_token text, p_events jsonb)` returns the accepted event count. `brief_ux_erase(p_token text)` removes browser-linked history. `brief_ux_maintain()` is service-role-only. The deployment registers current English public items before saving the content snapshots. Existing source evidence, classifications, Monthly Pulse subscribers and browser push subscription data are not changed by this feature.

## Security-advisor notes

The advisor reports that the private tables have RLS but no direct-access policies. That is intentional here: direct access is revoked and controlled RPCs perform the needed operations. It also flags anonymous SECURITY DEFINER functions, including the token-bound ingestion/withdrawal RPCs; these are intentionally public entrypoints, with restricted inputs and a fixed search path. Monitor abuse and reassess at scale. Unrelated existing warnings about `set_updated_at` and `citext` were not modified in this repair.

Supabase explanations: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy and https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable .

European Commission consent guidance: https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/legal-grounds-processing-data_en .
