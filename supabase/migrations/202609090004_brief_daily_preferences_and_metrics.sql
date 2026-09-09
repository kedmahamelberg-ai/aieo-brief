-- Additive migration. Existing newsletter subscribers and research data are untouched.
begin;
do $$ begin
 if to_regclass('public.brief_community_items') is null or to_regclass('public.brief_push_config') is null then
  raise exception 'Install the existing community and notifications migrations first.';
 end if;
end $$;
alter table public.brief_push_subscriptions add column if not exists topics text[] not null default array['news'];
alter table public.brief_push_subscriptions add column if not exists consent_version text not null default 'weekly-v1';

create or replace function public.brief_push_register_v2(p_endpoint text,p_p256dh text,p_auth text,p_token text,p_topics text[])
returns boolean language plpgsql security definer set search_path='' as $$
declare sid text; token_hash text; existing text;
begin
 if p_topics is null or cardinality(p_topics)<1 or cardinality(p_topics)>3 or array_position(p_topics,null) is not null or not (p_topics <@ array['news','culture','research']) then raise exception 'Choose at least one of the three categories';end if;
 if p_endpoint is null or length(p_endpoint)>2048 or p_endpoint !~ '^https://(fcm\.googleapis\.com/(fcm/send|wp)/|updates\.push\.services\.mozilla\.com/wpush/v[12]/|web\.push\.apple\.com/)[A-Za-z0-9_:/=+.-]+$' then raise exception 'Unsupported browser push endpoint';end if;
 if p_p256dh is null or p_p256dh !~ '^[A-Za-z0-9_-]{87}=?$' or p_auth is null or p_auth !~ '^[A-Za-z0-9_-]{22}(==)?$' or p_token is null or p_token !~ '^[a-f0-9]{64}$' then raise exception 'Invalid browser subscription';end if;
 if not exists(select 1 from public.brief_push_config where singleton and enabled and public_key<>'') then raise exception 'Notifications are not ready yet';end if;
 sid:=encode(sha256(convert_to(p_endpoint,'UTF8')),'hex');token_hash:=encode(sha256(convert_to(p_token,'UTF8')),'hex');
 perform pg_advisory_xact_lock(60260906);
 select s.manage_token_hash into existing from public.brief_push_subscriptions s where s.subscription_id=sid;
 if existing is not null and existing<>token_hash then return false;end if;
 if existing is null and ((select count(*) from public.brief_push_subscriptions)>=10000 or (select count(*) from public.brief_push_subscriptions where created_at>now()-interval '1 hour')>=200) then raise exception 'Please try again later';end if;
 insert into public.brief_push_subscriptions(subscription_id,endpoint,p256dh,auth_key,manage_token_hash,topics,consent_version)
 values(sid,p_endpoint,p_p256dh,p_auth,token_hash,array(select distinct unnest(p_topics)),'twice-daily-v2')
 on conflict(subscription_id) do update set p256dh=excluded.p256dh,auth_key=excluded.auth_key,topics=excluded.topics,consent_version=excluded.consent_version,updated_at=now();
 return true;
end $$;
create or replace function public.brief_push_preferences(p_endpoint text,p_token text)
returns jsonb language sql security definer set search_path='' as $$
 select jsonb_build_object('topics',s.topics,'consent_version',s.consent_version) from public.brief_push_subscriptions s where s.endpoint=p_endpoint and s.manage_token_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex');
$$;
create table if not exists public.brief_push_digest_deliveries (
 subscription_id text not null references public.brief_push_subscriptions on delete cascade,
 slot_key text not null check(slot_key ~ '^\d{4}-\d{2}-\d{2}-(am|pm)$'),
 state text not null check(state in ('sending','sent','failed')),
 attempts integer not null default 1 check(attempts between 1 and 3),
 updated_at timestamptz not null default now(),
 primary key(subscription_id,slot_key)
);
alter table public.brief_push_digest_deliveries enable row level security;
revoke all on public.brief_push_digest_deliveries from public,anon,authenticated;
grant select,insert,update,delete on public.brief_push_digest_deliveries to service_role;
create or replace function public.brief_push_due_slot() returns text language sql stable set search_path='' as $$
 select case when (now() at time zone 'Europe/Amsterdam')::time >= time '08:30' and (now() at time zone 'Europe/Amsterdam')::time < time '12:00' then to_char(now() at time zone 'Europe/Amsterdam','YYYY-MM-DD')||'-am'
 when (now() at time zone 'Europe/Amsterdam')::time >= time '18:30' and (now() at time zone 'Europe/Amsterdam')::time < time '22:00' then to_char(now() at time zone 'Europe/Amsterdam','YYYY-MM-DD')||'-pm' else null end;
$$;
create or replace function public.brief_push_digest_pending(p_slot text,p_limit integer default 500)
returns setof public.brief_push_subscriptions language sql security definer set search_path='' as $$
 select s.* from public.brief_push_subscriptions s left join public.brief_push_digest_deliveries d on d.subscription_id=s.subscription_id and d.slot_key=p_slot
 where p_slot=public.brief_push_due_slot() and s.consent_version='twice-daily-v2' and cardinality(s.topics)>0 and s.updated_at>now()-interval '180 days'
 and (d.subscription_id is null or (d.state<>'sent' and d.attempts<3 and d.updated_at<now()-interval '30 minutes'))
 order by s.subscription_id limit greatest(1,least(p_limit,500));
$$;
create or replace function public.brief_push_digest_claim(p_id text,p_slot text) returns boolean language plpgsql security definer set search_path='' as $$
declare claimed text;begin
 if p_slot is null or p_slot is distinct from public.brief_push_due_slot() then return false;end if;
 if not exists(select 1 from public.brief_push_config where singleton and enabled) or not exists(select 1 from public.brief_push_subscriptions where subscription_id=p_id and consent_version='twice-daily-v2' and cardinality(topics)>0) then return false;end if;
 insert into public.brief_push_digest_deliveries(subscription_id,slot_key,state) values(p_id,p_slot,'sending')
 on conflict(subscription_id,slot_key) do update set state='sending',attempts=public.brief_push_digest_deliveries.attempts+1,updated_at=now()
 where public.brief_push_digest_deliveries.state<>'sent' and public.brief_push_digest_deliveries.attempts<3 and public.brief_push_digest_deliveries.updated_at<now()-interval '30 minutes'
 returning subscription_id into claimed;return claimed is not null;
end $$;
create or replace function public.brief_push_digest_finish(p_id text,p_slot text) returns void language plpgsql security definer set search_path='' as $$
begin
 update public.brief_push_digest_deliveries set state='sent',updated_at=now() where subscription_id=p_id and slot_key=p_slot and state='sending';
end $$;
revoke all on function public.brief_push_register_v2(text,text,text,text,text[]),public.brief_push_preferences(text,text),public.brief_push_due_slot(),public.brief_push_digest_pending(text,integer),public.brief_push_digest_claim(text,text),public.brief_push_digest_finish(text,text) from public,anon,authenticated;
grant execute on function public.brief_push_register_v2(text,text,text,text,text[]),public.brief_push_preferences(text,text) to anon,authenticated;
grant execute on function public.brief_push_register_v2(text,text,text,text,text[]),public.brief_push_preferences(text,text),public.brief_push_due_slot(),public.brief_push_digest_pending(text,integer),public.brief_push_digest_claim(text,text),public.brief_push_digest_finish(text,text) to service_role;

-- Lifetime totals, backed by a bounded private deduplication ledger.
create table if not exists public.brief_engagement_totals (
 story_key text primary key references public.brief_community_items on delete cascade,
 views bigint not null default 0 check(views>=0),shares bigint not null default 0 check(shares>=0),
 started_at timestamptz not null default now()
);
create table if not exists public.brief_engagement_receipts (
 story_key text not null references public.brief_community_items on delete cascade,
 session_id uuid not null,kind text not null check(kind in ('view','share')),
 event_day date not null default ((now() at time zone 'UTC')::date),created_at timestamptz not null default now(),
 primary key(story_key,session_id,kind,event_day)
);
create index if not exists brief_engagement_session_day on public.brief_engagement_receipts(session_id,event_day);
create index if not exists brief_engagement_expiry on public.brief_engagement_receipts(event_day);
alter table public.brief_engagement_totals enable row level security;
alter table public.brief_engagement_receipts enable row level security;
revoke all on public.brief_engagement_totals,public.brief_engagement_receipts from public,anon,authenticated;
grant select,insert,update,delete on public.brief_engagement_totals,public.brief_engagement_receipts to service_role;
create or replace function public.brief_record_engagement(p_story_key text,p_session_id uuid,p_kind text)
returns boolean language plpgsql security definer set search_path='' as $$
declare inserted_key text;today date:=(now() at time zone 'UTC')::date;
begin
 if p_session_id is null or p_kind is null or p_kind not in ('view','share') then return false;end if;
 if not exists(select 1 from public.brief_community_items where story_key=p_story_key) then return false;end if;
 perform pg_advisory_xact_lock(hashtextextended(p_session_id::text,9092026));
 if (select count(*) from public.brief_engagement_receipts where session_id=p_session_id and event_day=today)>=500 then return false;end if;
 insert into public.brief_engagement_receipts(story_key,session_id,kind,event_day) values(p_story_key,p_session_id,p_kind,today) on conflict do nothing returning story_key into inserted_key;
 if inserted_key is null then return false;end if;
 insert into public.brief_engagement_totals(story_key,views,shares) values(p_story_key,case when p_kind='view' then 1 else 0 end,case when p_kind='share' then 1 else 0 end)
 on conflict(story_key) do update set views=public.brief_engagement_totals.views+excluded.views,shares=public.brief_engagement_totals.shares+excluded.shares;
 return true;
end $$;
create or replace function public.brief_community_metrics(p_keys text[]) returns jsonb language plpgsql security definer set search_path='' as $$
begin
 if coalesce(cardinality(p_keys),0)>250 then raise exception 'Too many story keys';end if;
 return coalesce((select jsonb_object_agg(i.story_key,jsonb_build_object(
 'views',coalesce(t.views,0),'shares',coalesce(t.shares,0),
 'likes',(select count(*) from public.brief_community_likes l where l.story_key=i.story_key),
 'saves',(select count(*) from public.brief_community_saves s where s.story_key=i.story_key),
 'comments',(select count(*) from public.brief_community_comments c where c.story_key=i.story_key and c.status='published'),
 'reads',(select count(*) from public.brief_community_reads r where r.story_key=i.story_key and r.read_date>=current_date-6),
 'liked',exists(select 1 from public.brief_community_likes l where l.story_key=i.story_key and l.user_id=auth.uid()),
 'saved',exists(select 1 from public.brief_community_saves s where s.story_key=i.story_key and s.user_id=auth.uid())))
 from public.brief_community_items i left join public.brief_engagement_totals t using(story_key) where i.story_key=any(p_keys)),'{}'::jsonb);
end $$;
create or replace function public.brief_community_maintain() returns integer language plpgsql security definer set search_path='' as $$
declare n integer;begin
 delete from public.brief_community_reads where read_date<current_date-90;get diagnostics n=row_count;
 delete from public.brief_engagement_receipts where event_day<(now() at time zone 'UTC')::date-8;
 delete from public.brief_push_digest_deliveries where updated_at<now()-interval '30 days';
 delete from public.brief_push_subscriptions where updated_at<now()-interval '180 days';
 return n;
end $$;
revoke all on function public.brief_record_engagement(text,uuid,text),public.brief_community_metrics(text[]),public.brief_community_maintain() from public,anon,authenticated;
grant execute on function public.brief_record_engagement(text,uuid,text),public.brief_community_metrics(text[]) to anon,authenticated,service_role;
grant execute on function public.brief_community_maintain() to service_role;
notify pgrst,'reload schema';
commit;
