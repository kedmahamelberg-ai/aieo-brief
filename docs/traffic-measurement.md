# The Brief traffic reports

Use the first-party totals for visible page loads. The reporting day follows Europe/Amsterdam. A visible navigation counts once. Reloads and returns from the browser’s back-forward cache can add a view. Automatic redirects count at the destination. The counts exclude obvious crawlers and previews, and depend on the browser running the measurement script. They do not estimate unique readers.

In the [Observatory project’s Supabase SQL editor](https://supabase.com/dashboard/project/tricsbvxamjzfeckivhz/sql/new), run this for the last 28 complete days. The project stores only daily aggregates. The legacy counter and the source totals increment in the same database transaction. The residual includes earlier views and visits from cached clients that still use the older counter.

```sql
with totals as (
  select day, sum(total) as views
  from brief_measurement_private.daily_counts
  where event = 'page_view'
  group by day
), sources as (
  select day, sum(total) as classified,
         sum(total) filter (where source = 'google') as google,
         sum(total) filter (where source = 'chatgpt') as chatgpt,
         sum(total) filter (where source = 'claude') as claude,
         sum(total) filter (where source = 'internal') as internal,
         sum(total) filter (where source = 'other_referral') as other_referral,
         sum(total) filter (where source = 'direct_or_unknown') as direct_or_unknown
  from brief_measurement_private.daily_page_view_sources
  group by day
), report_days as (
  select ((now() at time zone 'Europe/Amsterdam')::date - n)::date as day
  from generate_series(1, 28) as days(n)
)
select d.day, coalesce(t.views, 0) as page_views,
       coalesce(s.google, 0) as google,
       coalesce(s.chatgpt, 0) as chatgpt,
       coalesce(s.claude, 0) as claude,
       coalesce(s.internal, 0) as internal,
       coalesce(s.other_referral, 0) as other_referral,
       coalesce(s.direct_or_unknown, 0) as direct_or_unknown,
       coalesce(t.views, 0) - coalesce(s.classified, 0) as before_source_attribution
from report_days d
left join totals t using (day)
left join sources s using (day)
order by d.day desc;
```

Use [Search Console Web Performance filtered to The Brief](https://search.google.com/search-console/performance/search-analytics?resource_id=sc-domain%3Ahamelberg-ai.com&page=*https%3A%2F%2Fbrief.hamelberg-ai.com%2F) for Google impressions, clicks and search queries. In GA4, use Pages and screens with **Hostname exactly matches** `brief.hamelberg-ai.com`. The Brief and Observatory share a stream. GA4 stays in denied-storage consent mode, so visible first-party views can exceed GA4's reported views.

A recognised external referring hostname takes precedence over a known source tag. Internal links stay internal even with a source tag. Browsers and apps may omit the referrer, so untagged arrivals from those apps can be counted as direct or unknown. Referrals measure arrivals and Search Console measures Google search clicks.

Public article and weekly edition badges use these same page-load counts for the current Amsterdam
reporting day and the previous 29 days. The first-party history begins on
15 November 2026. The community endpoint returns only totals of at least three
for registered public articles and weekly editions. Each edition shows one
page-view total. Its two sections also have five-second reading counts.

Deploy the Supabase migration before publishing the corresponding JavaScript. After publishing, check that the page-view RPC returns HTTP 204 and that the expected source row increases. For controlled smoke tests, use recognisable referrers or `utm_source=google`, `utm_source=chatgpt.com` and `utm_source=claude.ai` on an existing public route. The request body should contain only the page path, broad device category and one source category. Controlled visits add to that day’s totals.
