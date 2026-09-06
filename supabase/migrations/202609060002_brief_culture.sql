-- Add cultural works to the existing moderated community, preserving its RLS.
-- Run after 202609060001_brief_community.sql; safe to run again.
begin;
alter table public.brief_community_items
  drop constraint if exists brief_community_items_story_key_check;
alter table public.brief_community_items add constraint brief_community_items_story_key_check
  check (story_key ~ '^(event:[0-9a-fA-F-]{36}|(paper|culture):[0-9a-f]{24})$');
alter table public.brief_community_items
  drop constraint if exists brief_community_items_kind_check;
alter table public.brief_community_items add constraint brief_community_items_kind_check
  check (kind in ('news','research','culture'));
commit;
