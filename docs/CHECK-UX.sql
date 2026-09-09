-- Read-only. No account changes, test data, email or model call.
select jsonb_build_object(
 'consent_rpc',to_regprocedure('public.brief_ux_consent(boolean,boolean,text)') is not null,
 'event_rpc',to_regprocedure('public.brief_ux_record(text,jsonb)') is not null,
 'erasure_rpc',to_regprocedure('public.brief_ux_erase(text)') is not null,
 'maintenance_rpc',to_regprocedure('public.brief_ux_maintain()') is not null,
 'content_versions',(select count(*) from public.brief_ux_content_versions),
 'events',(select count(*) from public.brief_behavior_events where event_schema_version='brief-ux-v1'),
 'research_rows',(select count(*) from public.brief_ux_research_events)
) as ux_readiness;
select event_name,count(*) as recorded_events,
 count(*) filter(where research_eligible) as research_eligible_events
from public.brief_behavior_events where event_schema_version='brief-ux-v1'
group by event_name order by recorded_events desc;
