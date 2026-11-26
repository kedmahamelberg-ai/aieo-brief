-- Applied through Supabase migration history. No individual event rows.
create schema if not exists brief_measurement_private;
revoke all on schema brief_measurement_private from public;
grant usage on schema brief_measurement_private to anon, authenticated, service_role;
create table brief_measurement_private.daily_counts (
 day date not null, page_path text not null, device text not null, event text not null,
 total bigint not null default 1 check(total > 0), primary key(day,page_path,device,event)
);
alter table brief_measurement_private.daily_counts enable row level security;
revoke all on brief_measurement_private.daily_counts from public, anon, authenticated;
grant select on brief_measurement_private.daily_counts to service_role;
create function brief_measurement_private.record(p_path text,p_device text,p_event text)
returns void language plpgsql security definer set search_path = '' as $$
begin
 -- Intentionally anonymous: auth.uid() would exclude ordinary readers.
 -- Privilege is limited to incrementing one strictly bounded aggregate cell.
 if p_path is null or length(p_path)>240 or p_path !~ '^/([a-z0-9-]+/)*$'
 or p_device is null or p_device not in ('desktop','mobile','tablet','other')
 or p_event is null or p_event not in ('page_view','engaged_read','source_open','share_option','save','unsave','like','unlike','support_link') then
  raise exception 'Invalid aggregate category' using errcode='22023';
 end if;
 delete from brief_measurement_private.daily_counts where day < ((now() at time zone 'Europe/Amsterdam') - interval '13 months')::date;
 insert into brief_measurement_private.daily_counts(day,page_path,device,event)
 values((now() at time zone 'Europe/Amsterdam')::date,p_path,p_device,p_event)
 on conflict(day,page_path,device,event) do update set total=brief_measurement_private.daily_counts.total+1;
end;
$$;
revoke all on function brief_measurement_private.record(text,text,text) from public;
grant execute on function brief_measurement_private.record(text,text,text) to anon, authenticated, service_role;
create function public.brief_record_aggregate(p_path text,p_device text,p_event text)
returns void language sql security invoker set search_path = '' as $$
 select brief_measurement_private.record(p_path,p_device,p_event);
$$;
revoke all on function public.brief_record_aggregate(text,text,text) from public;
grant execute on function public.brief_record_aggregate(text,text,text) to anon, authenticated, service_role;
