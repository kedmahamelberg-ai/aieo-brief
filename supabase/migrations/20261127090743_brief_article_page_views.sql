-- Expose only thresholded, 30-day page totals for registered public articles.
create index if not exists brief_daily_views_by_path_day
  on brief_measurement_private.daily_counts (page_path, day)
  where event = 'page_view';

create or replace function public.brief_community_metrics(p_keys text[])
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  report_day date := (now() at time zone 'Europe/Amsterdam')::date;
begin
  if coalesce(cardinality(p_keys), 0) > 250 then
    raise exception 'Too many story keys';
  end if;

  return coalesce((
    select jsonb_object_agg(i.story_key, jsonb_build_object(
      'page_views', page.page_views,
      'views', coalesce(t.views, 0),
      'shares', coalesce(t.shares, 0),
      'likes', (select count(*) from public.brief_community_likes l where l.story_key = i.story_key),
      'saves', (select count(*) from public.brief_community_saves s where s.story_key = i.story_key),
      'comments', (select count(*) from public.brief_community_comments c where c.story_key = i.story_key and c.status = 'published'),
      'reads', (select count(*) from public.brief_community_reads r where r.story_key = i.story_key and r.read_date >= current_date - 6),
      'liked', exists(select 1 from public.brief_community_likes l where l.story_key = i.story_key and l.user_id = auth.uid()),
      'saved', exists(select 1 from public.brief_community_saves s where s.story_key = i.story_key and s.user_id = auth.uid())
    ))
    from public.brief_community_items i
    left join public.brief_engagement_totals t using (story_key)
    left join lateral (
      select sum(c.total)::bigint as page_views
      from brief_measurement_private.daily_counts c
      where i.kind in ('news', 'research', 'culture')
        and i.url like 'https://brief.hamelberg-ai.com/%'
        and c.page_path = regexp_replace(
          split_part(split_part(substr(i.url, length('https://brief.hamelberg-ai.com') + 1), '#', 1), '?', 1),
          '/index[.]html$', '/'
        )
        and c.event = 'page_view'
        and c.day between report_day - 29 and report_day
      having sum(c.total) >= 3
    ) page on true
    where i.story_key = any(p_keys)
  ), '{}'::jsonb);
end;
$$;

revoke all on function public.brief_community_metrics(text[]) from public, anon, authenticated;
grant execute on function public.brief_community_metrics(text[]) to anon, authenticated, service_role;
notify pgrst, 'reload schema';
