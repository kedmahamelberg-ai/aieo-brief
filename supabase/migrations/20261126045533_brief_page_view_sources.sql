create table if not exists brief_measurement_private.daily_page_view_sources (
  day date not null,
  page_path text not null,
  source text not null check (
    source in ('google', 'chatgpt', 'claude', 'internal', 'other_referral', 'direct_or_unknown')
  ),
  total bigint not null default 1 check (total > 0),
  primary key (day, page_path, source)
);

alter table brief_measurement_private.daily_page_view_sources enable row level security;
revoke all on brief_measurement_private.daily_page_view_sources from public, anon, authenticated;
grant select on brief_measurement_private.daily_page_view_sources to service_role;

create or replace function brief_measurement_private.record_page_view(
  p_path text, p_device text, p_source text
)
returns void language plpgsql security definer set search_path = '' as $$
declare
  view_day date := (now() at time zone 'Europe/Amsterdam')::date;
begin
  -- Anonymous by design. The caller can increment fixed aggregate categories
  -- but cannot read counts, write arbitrary values or pass an identity.
  if p_source is null or p_source not in (
    'google', 'chatgpt', 'claude', 'internal', 'other_referral', 'direct_or_unknown'
  ) then
    raise exception 'Invalid page-view source' using errcode = '22023';
  end if;

  -- Validate the path and device and preserve the existing total atomically.
  perform brief_measurement_private.record(p_path, p_device, 'page_view');
  delete from brief_measurement_private.daily_page_view_sources
    where day < (view_day - interval '13 months')::date;
  insert into brief_measurement_private.daily_page_view_sources as c (day, page_path, source)
    values (view_day, p_path, p_source)
    on conflict (day, page_path, source)
    do update set total = c.total + 1;
end;
$$;

revoke all on function brief_measurement_private.record_page_view(text, text, text)
  from public;
grant execute on function brief_measurement_private.record_page_view(text, text, text)
  to anon, authenticated, service_role;

create or replace function public.brief_record_page_view(p_path text, p_device text, p_source text)
returns void language sql security invoker set search_path = '' as $$
  select brief_measurement_private.record_page_view(p_path, p_device, p_source);
$$;

revoke all on function public.brief_record_page_view(text, text, text) from public;
grant execute on function public.brief_record_page_view(text, text, text)
  to anon, authenticated, service_role;

notify pgrst, 'reload schema';
