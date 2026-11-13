-- Extend the existing validated page-name allowlist in place. Preserve all
-- consent, authentication, rate, payload, retention and privilege rules.
do $migration$
declare
  definition text;
  old_pages constant text := '''home'',''story'',''research'',''culture''';
  new_pages constant text := '''home'',''story'',''research'',''governments'',''culture''';
begin
  if to_regprocedure('public.brief_ux_record(text,jsonb)') is null then
    raise exception 'Install the existing Brief UX service before government engagement';
  end if;
  select pg_get_functiondef('public.brief_ux_record(text,jsonb)'::regprocedure) into definition;
  if strpos(definition, new_pages) > 0 then
    return;
  end if;
  if strpos(definition, old_pages) = 0 then
    raise exception 'Brief UX page allowlist changed; review before applying government engagement';
  end if;
  execute replace(definition, old_pages, new_pages);
end
$migration$;
