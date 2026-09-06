-- AIEO Brief community. Additive: no Observatory/evidence/auth tables are changed.
-- Run once in the SAME Supabase project as the Observatory.
begin;
create table if not exists public.brief_community_items (
  story_key text primary key check (story_key ~ '^(event:[0-9a-fA-F-]{36}|paper:[0-9a-f]{24})$'),
  headline text not null check (length(headline) between 1 and 500),
  url text not null check (url like 'https://%'),
  kind text not null check (kind in ('news','research')),
  published_date date not null,
  updated_at timestamptz not null default now()
);
create table if not exists public.brief_community_moderators (
  user_id uuid primary key references auth.users(id) on delete cascade
);
create table if not exists public.brief_community_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (length(display_name) between 2 and 40),
  created_at timestamptz not null default now()
);
create table if not exists public.brief_community_likes (
  story_key text not null references public.brief_community_items(story_key) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(), primary key(story_key,user_id)
);
create table if not exists public.brief_community_saves (
  story_key text not null references public.brief_community_items(story_key) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(), primary key(story_key,user_id)
);
create table if not exists public.brief_community_comments (
  id uuid primary key default gen_random_uuid(),
  story_key text not null references public.brief_community_items(story_key) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  parent_id uuid references public.brief_community_comments(id) on delete set null,
  display_name text not null check (length(display_name) between 2 and 40),
  body text not null check (length(body) between 10 and 2000),
  status text not null default 'pending' check (status in ('pending','published','rejected')),
  created_at timestamptz not null default now(), moderated_at timestamptz
);
create index if not exists brief_community_comments_story on public.brief_community_comments(story_key,status,created_at);
create table if not exists public.brief_community_reports (
  comment_id uuid not null references public.brief_community_comments(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  reason text not null check (length(reason) between 3 and 500), created_at timestamptz not null default now(),
  primary key(comment_id,user_id)
);
create table if not exists public.brief_community_reads (
  story_key text not null references public.brief_community_items(story_key) on delete cascade,
  session_id uuid not null, read_date date not null default current_date,
  active_seconds integer not null check (active_seconds between 20 and 3600),
  primary key(story_key,session_id,read_date)
);
create index if not exists brief_community_reads_date on public.brief_community_reads(read_date);
create table if not exists public.brief_sponsor_enquiries (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check(length(name) between 2 and 100),
  email text not null check(length(email) between 3 and 254),
  organisation text not null check(length(organisation) between 2 and 150),
  message text not null check(length(message) between 20 and 2500),created_at timestamptz not null default now()
);
-- Private source-support records are available only to server jobs.
create table if not exists public.brief_editorial_provenance (
 input_sha256 text primary key check(length(input_sha256)=64),
 proof jsonb not null, created_at timestamptz not null default now()
);
-- Only bounded RPCs are exposed; clients have no direct table access.
do $$ declare t text; begin
  foreach t in array array['brief_community_items','brief_community_moderators','brief_community_profiles','brief_community_likes','brief_community_saves','brief_community_comments','brief_community_reports','brief_community_reads','brief_sponsor_enquiries','brief_editorial_provenance'] loop
    execute format('alter table public.%I enable row level security',t);
    execute format('revoke all on public.%I from public, anon, authenticated',t);
    execute format('grant all on public.%I to service_role',t);
  end loop;
end $$;
create or replace function public.brief_community_uid() returns uuid language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=auth.uid(); begin
 if u is null or not exists(select 1 from auth.users where id=u and email_confirmed_at is not null) then raise exception 'Sign in with a verified email first.' using errcode='28000'; end if;
 return u;
end $$;
create or replace function public.brief_community_is_moderator() returns boolean language sql stable security definer set search_path=pg_catalog,public as $$
select exists(select 1 from public.brief_community_moderators where user_id=auth.uid());
$$;
create or replace function public.brief_community_metrics(p_keys text[]) returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if coalesce(array_length(p_keys,1),0)>250 then raise exception 'Too many story keys'; end if;
 return coalesce((select jsonb_object_agg(i.story_key,jsonb_build_object(
  'likes',(select count(*) from public.brief_community_likes l where l.story_key=i.story_key),
  'comments',(select count(*) from public.brief_community_comments c where c.story_key=i.story_key and c.status='published'),
  'reads',(select count(*) from public.brief_community_reads r where r.story_key=i.story_key and r.read_date>=current_date-6),
  'liked',exists(select 1 from public.brief_community_likes l where l.story_key=i.story_key and l.user_id=auth.uid()),
  'saved',exists(select 1 from public.brief_community_saves s where s.story_key=i.story_key and s.user_id=auth.uid())))
 from public.brief_community_items i where i.story_key=any(p_keys)),'{}'::jsonb);
end $$;
create or replace function public.brief_community_comments_for(p_story_key text) returns jsonb language sql security definer set search_path=pg_catalog,public as $$
select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at),'[]'::jsonb) from
(select id,parent_id,display_name,body,created_at,(user_id=auth.uid()) as mine from public.brief_community_comments where story_key=p_story_key and status='published' order by created_at desc,id desc limit 200) x;
$$;
create or replace function public.brief_community_toggle(p_story_key text,p_kind text,p_active boolean) returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid(); begin
 if p_active is null then raise exception 'An explicit state is required'; end if;
 if not exists(select 1 from public.brief_community_items where story_key=p_story_key) then raise exception 'Story is not registered'; end if;
 perform pg_advisory_xact_lock(hashtextextended(u::text,0));
 if p_kind='like' then
   if p_active then insert into public.brief_community_likes values(p_story_key,u,now()) on conflict do nothing;
   else delete from public.brief_community_likes where story_key=p_story_key and user_id=u; end if;
 elsif p_kind='save' then
   if p_active then insert into public.brief_community_saves values(p_story_key,u,now()) on conflict do nothing;
   else delete from public.brief_community_saves where story_key=p_story_key and user_id=u; end if;
 else raise exception 'Unknown activity';end if;
 return p_active;
end $$;
create or replace function public.brief_community_comment(p_story_key text,p_display_name text,p_body text,p_parent_id uuid default null) returns uuid language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid(); comment_id uuid; begin
 perform pg_advisory_xact_lock(hashtextextended(u::text,0));
 if (select count(*) from public.brief_community_comments where user_id=u and created_at>now()-interval '1 minute')>=3 then raise exception 'Please wait a minute before commenting again';end if;
 if p_parent_id is not null and not exists(select 1 from public.brief_community_comments where id=p_parent_id and story_key=p_story_key and status='published') then raise exception 'Reply target is unavailable';end if;
 p_display_name:=trim(p_display_name);p_body:=trim(p_body);
 insert into public.brief_community_profiles(user_id,display_name) values(u,p_display_name) on conflict(user_id) do update set display_name=excluded.display_name;
 insert into public.brief_community_comments(story_key,user_id,parent_id,display_name,body) values(p_story_key,u,p_parent_id,p_display_name,p_body) returning id into comment_id;
 return comment_id;
end $$;
create or replace function public.brief_community_delete_comment(p_id uuid) returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid();begin
 delete from public.brief_community_comments where id=p_id and user_id=u;return found;
end $$;
create or replace function public.brief_community_report(p_id uuid,p_reason text) returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid();begin
 if not exists(select 1 from public.brief_community_comments where id=p_id and status='published') then raise exception 'Comment unavailable';end if;
 insert into public.brief_community_reports(comment_id,user_id,reason) values(p_id,u,trim(p_reason)) on conflict do nothing; return true;
end $$;
create or replace function public.brief_community_record_read(p_story_key text,p_session_id uuid,p_active_seconds integer,p_progress numeric) returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if p_session_id is null or p_active_seconds is null or p_progress is null or p_active_seconds<20 or p_active_seconds>3600 or p_progress<0.5 or p_progress>1 then return false;end if;
 if not exists(select 1 from public.brief_community_items where story_key=p_story_key) then return false;end if;
 perform pg_advisory_xact_lock(hashtextextended(p_session_id::text,1));
 if (select count(*) from public.brief_community_reads where session_id=p_session_id and read_date=current_date)>=250 then return false;end if;
 insert into public.brief_community_reads values(p_story_key,p_session_id,current_date,p_active_seconds) on conflict do nothing;return found;
end $$;
create or replace function public.brief_community_my_data() returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid();begin
 return jsonb_build_object('profile',(select to_jsonb(p) from public.brief_community_profiles p where user_id=u),
 'likes',coalesce((select jsonb_agg(story_key) from public.brief_community_likes where user_id=u),'[]'::jsonb),
 'saves',coalesce((select jsonb_agg(story_key) from public.brief_community_saves where user_id=u),'[]'::jsonb),
 'comments',coalesce((select jsonb_agg(to_jsonb(c)) from public.brief_community_comments c where user_id=u),'[]'::jsonb),
 'moderator',public.brief_community_is_moderator());
end $$;
create or replace function public.brief_community_delete_profile() returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid();begin
 delete from public.brief_community_reports where user_id=u;
 delete from public.brief_community_comments where user_id=u;
 delete from public.brief_community_likes where user_id=u;
 delete from public.brief_community_saves where user_id=u;
 delete from public.brief_sponsor_enquiries where user_id=u;
 delete from public.brief_community_profiles where user_id=u;return true;
end $$;
create or replace function public.brief_community_moderation_queue() returns jsonb language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if not public.brief_community_is_moderator() then raise exception 'Moderator access required' using errcode='42501';end if;
 return jsonb_build_object('comments',coalesce((select jsonb_agg(to_jsonb(x)) from
 (select c.*,i.headline,i.url,(select jsonb_agg(r.reason) from public.brief_community_reports r where r.comment_id=c.id) as reports from public.brief_community_comments c join public.brief_community_items i using(story_key) where c.status='pending' or exists(select 1 from public.brief_community_reports where comment_id=c.id) order by c.created_at limit 200) x),'[]'::jsonb),
 'enquiries',coalesce((select jsonb_agg(to_jsonb(x)) from (select * from public.brief_sponsor_enquiries order by created_at desc limit 100) x),'[]'::jsonb));
end $$;
create or replace function public.brief_community_moderate(p_id uuid,p_status text) returns boolean language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 if not public.brief_community_is_moderator() then raise exception 'Moderator access required' using errcode='42501';end if;
 if p_status not in ('published','rejected') then raise exception 'Invalid decision';end if;
 update public.brief_community_comments set status=p_status,moderated_at=now() where id=p_id;
 delete from public.brief_community_reports where comment_id=p_id;return true;
end $$;
create or replace function public.brief_community_sponsor(p_name text,p_email text,p_organisation text,p_message text) returns uuid language plpgsql security definer set search_path=pg_catalog,public as $$
declare u uuid:=public.brief_community_uid(); item_id uuid;begin
 perform pg_advisory_xact_lock(hashtextextended(u::text,0));
 if (select count(*) from public.brief_sponsor_enquiries where user_id=u and created_at>now()-interval '1 day')>=3 then raise exception 'Please wait before sending another enquiry';end if;
 if not exists(select 1 from auth.users where id=u and lower(email)=lower(trim(p_email))) then raise exception 'Use the email you signed in with';end if;
 insert into public.brief_sponsor_enquiries(user_id,name,email,organisation,message) values(u,trim(p_name),trim(p_email),trim(p_organisation),trim(p_message)) returning id into item_id;return item_id;
end $$;
create or replace function public.brief_community_maintain() returns integer language plpgsql security definer set search_path=pg_catalog,public as $$
declare n integer;begin delete from public.brief_community_reads where read_date<current_date-90;get diagnostics n=row_count;return n;end $$;
-- Functions default to PUBLIC execute in PostgreSQL. Remove that default for
-- every function in this migration, including internal security-definer helpers.
do $$ declare f record; begin
 for f in select p.oid::regprocedure as signature from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'brief_community_%' loop
  execute format('revoke all on function %s from public, anon, authenticated',f.signature);
  execute format('grant execute on function %s to service_role',f.signature);
 end loop;
end $$;
grant execute on function public.brief_community_metrics(text[]), public.brief_community_comments_for(text),public.brief_community_record_read(text,uuid,integer,numeric) to anon,authenticated;
grant execute on function public.brief_community_toggle(text,text,boolean),public.brief_community_comment(text,text,text,uuid),public.brief_community_delete_comment(uuid),public.brief_community_report(uuid,text),public.brief_community_my_data(),public.brief_community_delete_profile(),public.brief_community_moderation_queue(),public.brief_community_moderate(uuid,text),public.brief_community_sponsor(text,text,text,text) to authenticated;
notify pgrst,'reload schema';
commit;
-- Make yourself a moderator after signing in to the Brief once. In a separate
-- SQL query, replace YOUR_EMAIL with your own address and run:
-- insert into public.brief_community_moderators(user_id)
-- select id from auth.users where lower(email)=lower('YOUR_EMAIL')
-- on conflict do nothing;
