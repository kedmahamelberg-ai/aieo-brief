import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const db=new PGlite();
await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;create schema auth;create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;grant usage on schema public,auth to anon,authenticated,service_role;`);
for(const file of ['202609060001_brief_community.sql','202609060002_brief_culture.sql','202609060003_brief_notifications.sql','202609090004_brief_daily_preferences_and_metrics.sql']){
 const sql=readFileSync('supabase/migrations/'+file,'utf8');await db.exec(sql);await db.exec(sql);
}
let checks=0;
const user='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
const key='culture:1234567890abcdef12345678';
await db.query(`insert into auth.users values($1,'reader@example.test',now())`,[user]);
await db.query(`insert into public.brief_community_items(story_key,headline,url,kind,published_date) values($1,'A daily pause','https://brief.example.test/culture/a/','culture',current_date)`,[key]);
await db.exec(`update public.brief_push_config set public_key='public-key',private_key='private-key',last_release='2026-W36';`);
// Deterministic server-clock fixture in this disposable database only.
await db.exec(`create or replace function public.brief_push_due_slot() returns text language sql stable set search_path='' as $$ select '2026-09-09-am'::text $$;`);
async function role(name,id=''){await db.exec('reset role');await db.query(`select set_config('request.jwt.claim.sub',$1,false)`,[id]);await db.exec('set role '+name);}
async function blocked(sql,args=[]){await assert.rejects(()=>db.query(sql,args));checks++;}
async function value(sql,args=[]){const r=await db.query(sql,args);return Object.values(r.rows[0])[0];}
const endpoint='https://fcm.googleapis.com/fcm/send/test',token='a'.repeat(64);
const subscribe=topics=>value('select public.brief_push_register_v2($1,$2,$3,$4,$5)',[endpoint,'x'.repeat(87),'y'.repeat(22),token,topics]);
await role('anon');
for(const name of ['brief_push_config','brief_push_subscriptions','brief_push_digest_deliveries','brief_engagement_receipts','brief_engagement_totals'])await blocked('select * from public.'+name);
await blocked("select public.brief_push_due_slot()");await blocked("select public.brief_push_digest_claim('id','2026-09-09-am')");
for(const topics of [['news'],['culture'],['research'],['news','research'],['news','culture','research']]){
 assert.equal(await subscribe(topics),true);
 const saved=await value('select public.brief_push_preferences($1,$2)',[endpoint,token]);
 assert.deepEqual(new Set(saved.topics),new Set(topics));assert.equal(saved.consent_version,'twice-daily-v2');checks++;
}
for(const topics of [[],['bad'],['news',null]])await assert.rejects(()=>subscribe(topics));checks++;
assert.equal(await value('select public.brief_push_preferences($1,$2)',[endpoint,'b'.repeat(64)]),null);checks++;
assert.equal(await value('select public.brief_record_engagement($1,$2,\'view\')',[key,user]),true);
assert.equal(await value('select public.brief_record_engagement($1,$2,\'view\')',[key,user]),false);checks++;
assert.equal(await value('select public.brief_record_engagement($1,$2,\'share\')',[key,user]),true);
assert.equal(await value('select public.brief_record_engagement($1,$2,\'share\')',[key,user]),false);checks++;
assert.equal(await value('select public.brief_record_engagement($1,$2,\'view\')',[key,other]),true);checks++;
assert.equal(await value('select public.brief_record_engagement($1,$2,\'bad\')',[key,user]),false);checks++;
await role('authenticated',user);await db.query("select public.brief_community_toggle($1,'like',true)",[key]);await db.query("select public.brief_community_toggle($1,'save',true)",[key]);
await role('anon');let metrics=await value('select public.brief_community_metrics($1)',[[key]]);
assert.equal(metrics[key].views,2);assert.equal(metrics[key].shares,1);assert.equal(metrics[key].likes,1);assert.equal(metrics[key].saves,1);assert.equal(metrics[key].liked,false);assert.equal(metrics[key].saved,false);assert.equal('user_id' in metrics[key],false);checks++;
await role('service_role');const sid=await value('select subscription_id from public.brief_push_subscriptions where endpoint=$1',[endpoint]);
assert.equal(await value('select public.brief_push_digest_claim($1,$2)',[sid,'2026-09-09-pm']),false);checks++;
assert.equal(await value('select public.brief_push_digest_claim($1,$2)',[sid,'2026-09-09-am']),true);
assert.equal(await value('select public.brief_push_digest_claim($1,$2)',[sid,'2026-09-09-am']),false);checks++;
await db.query('select public.brief_push_digest_finish($1,$2)',[sid,'2026-09-09-am']);
assert.equal(await value('select public.brief_push_digest_claim($1,$2)',[sid,'2026-09-09-am']),false);checks++;
// Old subscriptions retain weekly consent; they are not automatically upgraded.
await db.exec("update public.brief_push_subscriptions set consent_version='weekly-v1'");
assert.equal((await db.query("select * from public.brief_push_digest_pending('2026-09-09-am',500)")).rows.length,0);checks++;
await role('anon');assert.equal(await value('select public.brief_push_unsubscribe($1,$2)',[endpoint,token]),true);checks++;
await role('service_role');assert.equal((await db.query('select * from public.brief_push_digest_deliveries')).rows.length,0);checks++;
await db.query('select public.brief_community_maintain()');
// Public article counts use the first-party page rolls while the previous
// engagement totals and personalized fields remain available to existing callers.
await db.exec('reset role');
for (const file of [
 '20261115145059_brief_cookieless_aggregate_measurement.sql',
 '20261127090743_brief_article_page_views.sql'
]) await db.exec(readFileSync('supabase/migrations/'+file,'utf8'));
await db.query("update public.brief_community_items set url='https://brief.hamelberg-ai.com/culture/a/index.html?campaign=example#read' where story_key=$1",[key]);
const wrongHost='culture:1234567890abcdef12345679';
await db.query("insert into public.brief_community_items(story_key,headline,url,kind,published_date) values($1,'Other host','https://example.test/culture/a/','culture',current_date)",[wrongHost]);
await db.exec(`
  insert into brief_measurement_private.daily_counts(day,page_path,device,event,total)
  values ((now() at time zone 'Europe/Amsterdam')::date, '/culture/a/', 'desktop', 'page_view', 2),
         ((now() at time zone 'Europe/Amsterdam')::date - 30, '/culture/a/', 'desktop', 'page_view', 30),
         ((now() at time zone 'Europe/Amsterdam')::date, '/culture/a/', 'desktop', 'engaged_read', 9),
         ((now() at time zone 'Europe/Amsterdam')::date, '/culture/b/', 'mobile', 'page_view', 10);
`);
await role('anon');
await blocked('select * from brief_measurement_private.daily_counts');
metrics=await value('select public.brief_community_metrics($1)',[[key,wrongHost,'unknown']]);
assert.equal(metrics[key].page_views,null);
assert.equal(metrics[wrongHost].page_views,null);
assert.equal(metrics.unknown,undefined);checks+=3;
await db.exec('reset role');
await db.exec(`
  insert into brief_measurement_private.daily_counts(day,page_path,device,event,total)
  values ((now() at time zone 'Europe/Amsterdam')::date - 29, '/culture/a/', 'mobile', 'page_view', 4)
`);
await role('authenticated',user);
metrics=await value('select public.brief_community_metrics($1)',[[key]]);
assert.equal(metrics[key].page_views,6);
assert.equal(metrics[key].views,2);
assert.equal(metrics[key].shares,1);
assert.equal(metrics[key].liked,true);
assert.equal(metrics[key].saved,true);checks+=5;
console.log(JSON.stringify({daily_preferences_and_metrics_checks:checks,migration_runs:10}));await db.close();
