// Synthetic in-memory PostgreSQL only. No production connection or rows.
// Run with EVIDENCE_SQL_TEST_ENGINE pointing at an isolated @electric-sql/pglite install.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {PGlite} = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const db = new PGlite();
const legacy = ['ai_competitor_enrichment_queue','ai_visibility_queries','ai_visibility_results','business_aliases',
    'business_classifications','business_entity_aliases','business_platform_links','business_reviews','businesses',
    'cohort_memberships','competitor_relationship_reviews','data_imports','google_profiles','locations',
    'raw_outscraper_locations','review_analysis_runs','review_import_batches','review_themes','website_audit_pages',
    'website_audit_runs'];
// Reproduce the live starting point: Supabase roles, default grants to the API roles, RLS on, no policies.
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
create schema auth; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated, service_role;
create table public.business_features(google_place_id text unique);
create table public.ai_visibility_runs(id uuid primary key, target_google_place_id text);
create sequence public.legacy_seq;
${legacy.map(t => `create table public.${t}(id int);`).join('\n')}
${[...legacy,'business_features','ai_visibility_runs'].map(t => `alter table public.${t} enable row level security;`).join('\n')}`);
const can = async (role, table, privilege) =>
    (await db.query('select has_table_privilege($1,$2,$3) ok', [role, `public.${table}`, privilege])).rows[0].ok;
assert.equal(await can('anon', 'ai_visibility_runs', 'select'), true, 'fixture should start with the legacy grants');

for (const file of ['20261001124625_evidence_foundations.sql', '20261001160431_evidence_foundation_service_permissions.sql',
    '20261003120000_revoke_legacy_client_grants.sql', '20261003120100_customer_free_checks.sql']) {
    await db.exec(await readFile(`sql/${file}`, 'utf8'));
}

// 1. Legacy grants are gone, and new tables no longer inherit them.
for (const table of [...legacy, 'business_features', 'ai_visibility_runs']) {
    for (const role of ['anon', 'authenticated']) {
        for (const privilege of ['select', 'insert', 'update', 'delete', 'truncate']) {
            assert.equal(await can(role, table, privilege), false, `${role} ${privilege} ${table}`);
        }
    }
}
assert.equal((await db.query("select has_sequence_privilege('anon','public.legacy_seq','usage') ok")).rows[0].ok, false);
await db.exec('create table public.future_table(id int)');
assert.equal(await can('anon', 'future_table', 'select'), false);
assert.equal(await can('authenticated', 'future_table', 'insert'), false);
assert.equal(await can('service_role', 'future_table', 'select'), true, 'service_role defaults are untouched');

// 2. Customer checks.
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const [alice, bob] = [id(1), id(2)];
await db.query('insert into auth.users values ($1),($2)', [alice, bob]);
const questions = [1, 2, 3, 4, 5].map(n => `Where can I find good private dining option ${n} in Hove?`);
const submit = (owner, key, qs = questions, calls = 15) => db.query(
    'select * from public.submit_customer_check($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    [owner, key, 'Synthetic Bistro', ' ', 'Hove', 'private dining', ['Rival One'], qs, calls]);
const as = async (role, user, work) => {
    await db.exec(`set role ${role}; select set_config('request.jwt.claim.sub','${user ?? ''}',false)`);
    try { return await work(); } finally { await db.exec('reset role'); }
};

await db.exec('set role service_role');
const first = (await submit(alice, 'alice-key-000000001')).rows[0];
assert.equal(first.status, 'queued');
assert.equal(first.website, null, 'blank website is stored as null');
const again = (await submit(alice, 'alice-key-000000001')).rows[0];
assert.equal(again.id, first.id, 'same key returns the same check');
assert.equal((await db.query('select count(*)::int n from public.visibility_jobs')).rows[0].n, 1, 'no second job reserved');
await assert.rejects(submit(alice, 'alice-key-000000002'), /unique|duplicate/i, 'one free check per account');
await assert.rejects(submit(bob, 'bob-key-0000000001', questions.slice(0, 4)), /check constraint/i);
await assert.rejects(submit(bob, 'short'), /check constraint/i);
await assert.rejects(submit(bob, 'bob-key-0000000001', questions, 0), /check constraint/i);
assert.equal((await db.query('select count(*)::int n from public.customer_checks')).rows[0].n, 1, 'failed submissions leave nothing behind');
const bobs = (await submit(bob, 'bob-key-0000000001')).rows[0];

// The submitted brief and its owner are frozen; lifecycle fields are not.
await assert.rejects(db.query("update public.customer_checks set questions[1]='A different question entirely?' where id=$1", [first.id]), /cannot be changed/i);
await assert.rejects(db.query('update public.customer_checks set owner_user_id=$2 where id=$1', [first.id, bob]), /cannot be changed/i);
await assert.rejects(db.query("update public.customer_checks set result_projection='{}' where id=$1", [first.id]), /check constraint/i);
await db.query("update public.customer_checks set status='completed', result_projection='{\"schema\":1}', result_projection_version='v1' where id=$1", [first.id]);
await assert.rejects(db.query('delete from public.customer_checks where id=$1', [first.id]), /permission denied/i);

// Job lease rules.
const job = (await db.query('select id from public.visibility_jobs where check_id=$1', [bobs.id])).rows[0].id;
await assert.rejects(db.query("update public.visibility_jobs set state='leased' where id=$1", [job]), /check constraint/i);
await db.query("update public.visibility_jobs set state='leased', lease_owner='worker-1', lease_expires_at=now()+interval '5 minutes', attempt_count=1 where id=$1", [job]);
await assert.rejects(db.query("update public.visibility_jobs set state='failed' where id=$1", [job]), /check constraint/i);
await assert.rejects(db.query('update public.visibility_jobs set check_id=$2 where id=$1', [job, first.id]), /another check/i);
await db.query("update public.visibility_jobs set state='failed', lease_owner=null, lease_expires_at=null, completed_at=now(), last_error='provider unavailable' where id=$1", [job]);
// A check that failed outright releases the free entitlement.
await db.query("update public.customer_checks set status='failed', error_code='provider_unavailable' where id=$1", [bobs.id]);
const retry = (await submit(bob, 'bob-key-0000000002')).rows[0];
assert.notEqual(retry.id, bobs.id);
await db.exec('reset role');

// Customers read only their own checks and write nothing.
assert.deepEqual(await as('authenticated', alice, async () =>
    (await db.query('select id from public.customer_checks')).rows.map(r => r.id)), [first.id]);
assert.equal(await as('authenticated', bob, async () =>
    (await db.query('select count(*)::int n from public.customer_checks')).rows[0].n), 2);
assert.equal(await as('authenticated', null, async () =>
    (await db.query('select count(*)::int n from public.customer_checks')).rows[0].n), 0);
for (const [role, user, sql] of [
    ['anon', null, 'select 1 from public.customer_checks'],
    ['authenticated', alice, 'select 1 from public.visibility_jobs'],
    ['authenticated', alice, `update public.customer_checks set status='queued' where id='${first.id}'`],
    ['authenticated', alice, `delete from public.customer_checks where id='${first.id}'`],
    ['authenticated', alice, `insert into public.customer_checks(owner_user_id,idempotency_key,business_name,location,services,questions) values ('${alice}','direct-key-00000001','x','y','z','{}')`],
    ['authenticated', bob, `select * from public.submit_customer_check('${bob}','bob-key-0000000003','x',null,'y','z','{}','{}',15)`],
    ['authenticated', alice, 'select 1 from public.ai_visibility_runs'],
]) {
    await assert.rejects(as(role, user, () => db.query(sql)), /permission denied/i, `${role}: ${sql}`);
}

// Free-check runs are marked on the wave itself; unknown kinds are still rejected.
await db.query("insert into public.ai_visibility_runs values ($1,'place'),($2,'place')", [id(20), id(21)]);
const wave = kind => db.query(`insert into public.ai_measurement_waves(run_id,series_id,panel_id,panel_kind,configuration_sha256,configuration)
    values($1,$2,$3,$4,$3,$5::jsonb)`, [kind === 'free_check' ? id(20) : id(21), id(30), 'a'.repeat(64), kind,
    JSON.stringify({version: 'measurement-panel-v1', panel_kind: kind})]);
await wave('free_check');
await assert.rejects(wave('invented'), /check constraint/i);

// Deleting the account removes its checks and jobs.
await db.query('delete from auth.users where id=$1', [bob]);
assert.equal((await db.query('select count(*)::int n from public.customer_checks')).rows[0].n, 1);
assert.equal((await db.query('select count(*)::int n from public.visibility_jobs')).rows[0].n, 1);
console.log('free check migrations: all synthetic checks passed');
