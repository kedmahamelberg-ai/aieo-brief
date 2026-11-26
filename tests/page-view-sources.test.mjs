import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
for (const suffix of ['_brief_cookieless_aggregate_measurement.sql', '_brief_page_view_sources.sql']) {
 const migration = readdirSync('supabase/migrations').find(file => file.endsWith(suffix));
 await db.exec(readFileSync('supabase/migrations/' + migration, 'utf8'));
}
await db.exec('set role anon;');
const record = (source, path = '/story/example/') =>
 db.query("select public.brief_record_page_view($1, 'desktop', $2)", [path, source]);

// An old client may still add a view to the historical total.
await db.query("select public.brief_record_aggregate('/story/example/', 'desktop', 'page_view')");
for (const source of ['google', 'google', 'chatgpt', 'claude', 'internal', 'other_referral', 'direct_or_unknown']) {
 await record(source);
}
await assert.rejects(() => record('https://claude.ai/chat/private'));
await assert.rejects(() => record('claude', '/story/example/?secret=value'));
await assert.rejects(() => db.query('select * from brief_measurement_private.daily_page_view_sources'));
await assert.rejects(() => db.query('select * from brief_measurement_private.daily_counts'));
await db.exec('reset role; set role service_role;');
const sources = await db.query('select source, total::int from brief_measurement_private.daily_page_view_sources');
assert.deepEqual(Object.fromEntries(sources.rows.map(row => [row.source, row.total])), {
 google: 2, chatgpt: 1, claude: 1, internal: 1, other_referral: 1, direct_or_unknown: 1
});
const counts = await db.query("select total::int from brief_measurement_private.daily_counts where event = 'page_view'");
assert.deepEqual(counts.rows, [{total: 8}]);
await db.close();
console.log('Page-view totals, source buckets and database permissions verified.');
