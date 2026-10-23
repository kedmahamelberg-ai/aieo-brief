-- Register each weekly news and research reading as its own community item.
-- The existing tables, RPCs, RLS policies and public-count rules stay in place.
begin;
alter table public.brief_community_items
  drop constraint if exists brief_community_items_story_key_check;
alter table public.brief_community_items
  add constraint brief_community_items_story_key_check
  check (story_key ~ '^(event:[0-9a-fA-F-]{36}|(paper|culture):[0-9a-f]{24}|weekly:[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3]):(markets|research))$');
alter table public.brief_community_items
  drop constraint if exists brief_community_items_kind_check;
alter table public.brief_community_items
  add constraint brief_community_items_kind_check
  check (kind in ('news','research','culture','weekly_news','weekly_research'));
commit;
