-- Run once in the existing Supabase SQL Editor. Safe to run again.
-- Private delivery keys and browser endpoints are never publicly readable.
begin;
create table if not exists public.brief_push_config (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default true,
  private_key text not null default '',
  public_key text not null default '',
  last_release text not null default '',
  updated_at timestamptz not null default now()
);
insert into public.brief_push_config(singleton) values(true) on conflict do nothing;
create table if not exists public.brief_push_subscriptions (
  subscription_id text primary key,
  endpoint text not null unique,
  p256dh text not null,
  auth_key text not null,
  manage_token_hash text not null,
  last_release text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists public.brief_push_deliveries (
  subscription_id text not null references public.brief_push_subscriptions on delete cascade,
  release_id text not null,
  state text not null check(state in ('sending','sent','failed')),
  attempts integer not null default 1,
  updated_at timestamptz not null default now(),
  primary key(subscription_id, release_id)
);
alter table public.brief_push_config enable row level security;
alter table public.brief_push_subscriptions enable row level security;
alter table public.brief_push_deliveries enable row level security;
revoke all on public.brief_push_config, public.brief_push_subscriptions, public.brief_push_deliveries from public, anon, authenticated;
grant select, insert, update, delete on public.brief_push_config, public.brief_push_subscriptions, public.brief_push_deliveries to service_role;

create or replace function public.brief_push_register(p_endpoint text, p_p256dh text, p_auth text, p_token text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare sid text; token_hash text; current_edition text; existing text;
begin
  if p_endpoint is null or length(p_endpoint)>2048 or
     p_endpoint !~ '^https://(fcm\.googleapis\.com/(fcm/send|wp)/|updates\.push\.services\.mozilla\.com/wpush/v[12]/|web\.push\.apple\.com/)[A-Za-z0-9_:/=+.-]+$' then
    raise exception 'Unsupported browser push endpoint';
  end if;
  if p_p256dh is null or p_p256dh !~ '^[A-Za-z0-9_-]{87}=?$' or
     p_auth is null or p_auth !~ '^[A-Za-z0-9_-]{22}(==)?$' or
     p_token is null or p_token !~ '^[a-f0-9]{64}$' then
    raise exception 'Invalid browser subscription';
  end if;
  select c.last_release into current_edition from public.brief_push_config c
    where c.singleton and c.enabled and c.public_key<>'';
  if current_edition is null or current_edition !~ '^\d{4}-W\d{2}$' then
    raise exception 'News alerts are not ready yet';
  end if;
  sid := encode(sha256(convert_to(p_endpoint,'UTF8')), 'hex');
  token_hash := encode(sha256(convert_to(p_token,'UTF8')), 'hex');
  -- Serialize creation and enforce a bound against unauthenticated flooding.
  perform pg_advisory_xact_lock(60260906);
  select s.manage_token_hash into existing from public.brief_push_subscriptions s where s.subscription_id=sid;
  if existing is not null and existing<>token_hash then return false; end if;
  if existing is null and ((select count(*) from public.brief_push_subscriptions)>10000 or
      (select count(*) from public.brief_push_subscriptions where created_at>now()-interval '1 hour')>=200) then
    raise exception 'Please try again later';
  end if;
  insert into public.brief_push_subscriptions(subscription_id,endpoint,p256dh,auth_key,manage_token_hash,last_release)
    values(sid,p_endpoint,p_p256dh,p_auth,token_hash,current_edition)
  on conflict(subscription_id) do update set p256dh=excluded.p256dh, auth_key=excluded.auth_key, updated_at=now();
  return true;
end $$;

create or replace function public.brief_push_unsubscribe(p_endpoint text, p_token text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  delete from public.brief_push_subscriptions where endpoint=p_endpoint
    and manage_token_hash=encode(sha256(convert_to(p_token,'UTF8')), 'hex');
  return found;
end $$;

-- Only the server can claim a delivery. Concurrent workflow runs cannot send
-- the same edition to the same reader; abandoned claims retry after an hour.
create or replace function public.brief_push_claim(p_id text, p_release text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare claimed text;
begin
  if p_release !~ '^\d{4}-W\d{2}$' then raise exception 'Invalid edition'; end if;
  if not exists(select 1 from public.brief_push_subscriptions where subscription_id=p_id and last_release<p_release) then return false; end if;
  insert into public.brief_push_deliveries(subscription_id,release_id,state) values(p_id,p_release,'sending')
  on conflict(subscription_id,release_id) do update set state='sending', attempts=public.brief_push_deliveries.attempts+1, updated_at=now()
    where public.brief_push_deliveries.state<>'sent' and public.brief_push_deliveries.attempts<5
      and public.brief_push_deliveries.updated_at<now()-interval '1 hour'
  returning subscription_id into claimed;
  return claimed is not null;
end $$;
revoke all on function public.brief_push_register(text,text,text,text), public.brief_push_unsubscribe(text,text), public.brief_push_claim(text,text) from public;
grant execute on function public.brief_push_register(text,text,text,text), public.brief_push_unsubscribe(text,text) to anon, authenticated;
revoke all on function public.brief_push_claim(text,text) from anon, authenticated;
grant execute on function public.brief_push_claim(text,text) to service_role;

create or replace function public.brief_push_pending(p_release text, p_limit integer default 500)
returns setof public.brief_push_subscriptions language sql security definer set search_path = '' as $$
  select s.* from public.brief_push_subscriptions s
  left join public.brief_push_deliveries d on d.subscription_id=s.subscription_id and d.release_id=p_release
  where s.last_release<p_release and s.updated_at>now()-interval '180 days'
    and (d.subscription_id is null or (d.state<>'sent' and d.attempts<5 and d.updated_at<now()-interval '1 hour'))
  order by s.subscription_id limit greatest(1,least(p_limit,500));
$$;
create or replace function public.brief_push_finish(p_id text, p_release text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.brief_push_deliveries set state='sent', updated_at=now() where subscription_id=p_id and release_id=p_release;
  update public.brief_push_subscriptions set last_release=p_release where subscription_id=p_id and last_release<p_release;
end $$;
revoke all on function public.brief_push_pending(text,integer), public.brief_push_finish(text,text) from public, anon, authenticated;
grant execute on function public.brief_push_pending(text,integer), public.brief_push_finish(text,text) to service_role;
commit;
