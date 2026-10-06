// Synthetic in-memory PostgreSQL only. No production connection or rows.
// Run with EVIDENCE_SQL_TEST_ENGINE pointing at an isolated @electric-sql/pglite install.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {PGlite} = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
alter default privileges in schema public grant all on tables to service_role;
create schema auth; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated, service_role;
create table public.business_features(google_place_id text unique, business_name text, raw_category text);
create table public.raw_outscraper_locations(id serial primary key, google_place_id text, raw_data jsonb, created_at timestamptz default now());
create table public.ai_visibility_runs(id uuid primary key, target_google_place_id text);
${['ai_competitor_enrichment_queue','ai_visibility_queries','ai_visibility_results','business_aliases','business_classifications',
    'business_entity_aliases','business_platform_links','business_reviews','businesses','cohort_memberships',
    'competitor_relationship_reviews','data_imports','google_profiles','locations',
    'review_analysis_runs','review_import_batches','review_themes','website_audit_pages','website_audit_runs']
    .map(t => `create table public.${t}(id int);`).join('\n')}
insert into public.business_features values
  ('lion','The Lion & Lobster','Pub'),('burger','Burger & Lobster - Brighton','Restaurant'),
  ('cafe-a','Synthetic Coffee','Cafe'),('cafe-b','Synthetic Coffee','Cafe'),
  ('roast','Synthetic Coffee Roasters Hove','Cafe'),('long','Bistro','Restaurant'),('pub','The Pub','Pub');
insert into public.raw_outscraper_locations(google_place_id, raw_data, created_at) values
  ('lion','{"street":"Old Street","city":"Brighton"}', now() - interval '2 days'),
  ('lion','{"street":"24 Sillwood Street","city":"Brighton"}', now()),
  ('cafe-a','{"street":"1 North Road","city":"Brighton"}', now()),
  ('cafe-b','{"street":" ","city":"Hove"}', now());`);
for (const file of ['20261001124625_evidence_foundations.sql', '20261003120000_revoke_legacy_client_grants.sql',
    '20261003120100_customer_free_checks.sql', '20261006100000_free_check_business_match.sql']) {
    await db.exec(await readFile(`sql/${file}`, 'utf8'));
}
const match = async (name, limit = 3) =>
    (await db.query('select * from public.match_business_directory($1,$2)', [name, limit])).rows;
const ids = async (name, limit) => (await match(name, limit)).map(r => r.google_place_id);
await db.exec('set role service_role');

// The spelling the owner types still finds the listing, with its latest street.
for (const typed of ['Lion & Lobster', 'the lion and lobster', 'LION AND LOBSTER!', "Lion 'n' Lobster".replace("'n'", '&')]) {
    assert.deepEqual(await ids(typed), ['lion'], typed);
}
assert.deepEqual((await match('Lion & Lobster'))[0],
    {google_place_id: 'lion', business_name: 'The Lion & Lobster', street: '24 Sillwood Street', city: 'Brighton', category: 'Pub'});
// A similar-sounding business is not offered.
assert.equal((await ids('Lion & Lobster')).includes('burger'), false);
assert.deepEqual(await ids('Burger and Lobster'), ['burger'], 'a partial name finds the longer listing');
// Same-named branches are both offered, told apart by address; exact matches come first.
const branches = await match('Synthetic Coffee', 5);
assert.deepEqual(branches.map(r => r.google_place_id), ['cafe-a', 'cafe-b', 'roast']);
assert.equal(branches[1].street, null, 'a blank street is not shown');
assert.equal((await ids('Synthetic Coffee', 2)).length, 2);
assert.equal((await ids('Synthetic Coffee', 99)).length, 3, 'the limit is capped');
// Generic or tiny input cannot fish for unrelated businesses.
assert.deepEqual(await ids('bistro'), ['long'], 'a short generic word only matches exactly');
assert.deepEqual(await ids('pub'), ['pub'], 'a leading The is ignored for an exact match');
assert.deepEqual(await ids('co'), []);
assert.deepEqual(await ids(''), []);
assert.deepEqual(await ids('%'), []);
assert.deepEqual(await ids('Nothing Like It Anywhere'), []);

// Submitting with and without a confirmed listing.
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
await db.exec('reset role');
await db.query('insert into auth.users values ($1),($2),($3)', [id(1), id(2), id(3)]);
await db.exec('set role service_role');
const questions = [1, 2, 3, 4, 5].map(n => `Where can I find good private dining option ${n} in Hove?`);
const base = n => [id(n), `synthetic-key-${String(n).padStart(6, '0')}`, 'Lion & Lobster', null, 'Brighton', 'good pub atmosphere', [], questions, 15];
const claimed = (await db.query('select * from public.submit_customer_check($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)', [...base(1), 'lion'])).rows[0];
assert.equal(claimed.claimed_google_place_id, 'lion');
const unclaimed = (await db.query('select * from public.submit_customer_check($1,$2,$3,$4,$5,$6,$7,$8,$9)', base(2))).rows[0];
assert.equal(unclaimed.claimed_google_place_id, null, 'the earlier nine-argument call still works');
await assert.rejects(db.query('select * from public.submit_customer_check($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)', [...base(3), 'not-a-listing']), /foreign key/i);
assert.equal((await db.query('select count(*)::int n from public.visibility_jobs')).rows[0].n, 2, 'a rejected listing leaves no job');
await assert.rejects(db.query("update public.customer_checks set claimed_google_place_id='burger' where id=$1", [claimed.id]), /cannot be changed/i);
await db.query("update public.customer_checks set status='running' where id=$1", [claimed.id]);
await db.exec('reset role');

// Customers can call none of it.
for (const sql of ["select * from public.match_business_directory('Lion & Lobster', 3)",
                   "select public.normalise_business_name('x')",
                   `select * from public.submit_customer_check('${id(3)}','synthetic-key-000009','x',null,'y','z','{}','{}',15,'lion')`]) {
    for (const role of ['anon', 'authenticated']) {
        await db.exec(`set role ${role}`);
        try { await assert.rejects(db.query(sql), /permission denied/i, `${role}: ${sql}`); } finally { await db.exec('reset role'); }
    }
}
console.log('free check business match: all synthetic checks passed');
