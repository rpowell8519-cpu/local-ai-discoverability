// Synthetic in-memory PostgreSQL only. No production connection or rows.
// Runs the exact SQL statements from src/free_check_jobs.py against the real migrations.
// Run with EVIDENCE_SQL_TEST_ENGINE pointing at an isolated @electric-sql/pglite install.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {PGlite} = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const python = process.env.FREE_CHECK_PYTHON || '.venv/bin/python';
const SQL = JSON.parse(execFileSync(python, ['-c',
    "import json, src.free_check_jobs as j; print(json.dumps({k: v for k, v in vars(j).items() if k.endswith('_SQL')}))"],
    {encoding: 'utf8'}));
const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
create table public.business_features(google_place_id text unique);
create table public.ai_visibility_runs(id uuid primary key, target_google_place_id text, started_at timestamptz default now());
${['ai_competitor_enrichment_queue','ai_visibility_queries','ai_visibility_results','business_aliases','business_classifications',
    'business_entity_aliases','business_platform_links','business_reviews','businesses','cohort_memberships',
    'competitor_relationship_reviews','data_imports','google_profiles','locations','raw_outscraper_locations',
    'review_analysis_runs','review_import_batches','review_themes','website_audit_pages','website_audit_runs']
    .map(t => `create table public.${t}(id int);`).join('\n')}`);
for (const file of ['20261001124625_evidence_foundations.sql', '20261003120000_revoke_legacy_client_grants.sql',
    '20261003120100_customer_free_checks.sql']) {
    await db.exec(await readFile(`sql/${file}`, 'utf8'));
}
// SQLAlchemy :name parameters -> positional parameters, reusing one position per name.
const run = async (name, params = {}) => {
    const order = [];
    const sql = SQL[name].replace(/(?<!:):([a-z_]+)/g, (_, key) => {
        if (!order.includes(key)) order.push(key);
        return `$${order.indexOf(key) + 1}`;
    });
    for (const key of order) assert.ok(key in params, `${name} needs ${key}`);
    return db.query(sql, order.map(key => params[key]));
};
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const questions = [1, 2, 3, 4, 5].map(n => `Where can I find good private dining option ${n} in Hove?`);
const submit = async n => {
    await db.query('insert into auth.users values ($1)', [id(n)]);
    return (await db.query('select * from public.submit_customer_check($1,$2,$3,$4,$5,$6,$7,$8,$9)',
        [id(n), `synthetic-key-${String(n).padStart(6, '0')}`, 'Synthetic Bistro', null, 'Hove', 'private dining', [], questions, 15])).rows[0];
};
const job = async checkId => (await db.query('select * from public.visibility_jobs where check_id=$1', [checkId])).rows[0];
const check = async checkId => (await db.query('select * from public.customer_checks where id=$1', [checkId])).rows[0];
const claim = async (worker, allowNew = true) =>
    (await run('CLAIM_SQL', {worker_id: worker, lease_seconds: 600, allow_new: allowNew})).rows[0];

const first = await submit(1);
const second = await submit(2);
assert.equal((await run('STARTED_TODAY_SQL')).rows[0].count, 0);

// Claim the oldest job; a second worker gets the next one, never the same one.
const leased = await claim('worker-a');
assert.equal(leased.check_id, first.id);
assert.equal(leased.attempt_count, 1);
assert.equal(leased.state, 'leased');
await run('MARK_RUNNING_SQL', {id: first.id});
assert.equal((await check(first.id)).status, 'running');
assert.equal((await run('LOAD_CHECK_SQL', {id: first.id})).rows[0].questions.length, 5);

// With the daily cap reached, a job that has no run yet stays queued.
assert.equal(await claim('worker-b', false), undefined);

// Attaching the run links job and check; only the lease holder may do it, and only once.
await db.query('insert into public.ai_visibility_runs(id,target_google_place_id) values ($1,$2)', [id(50), 'discovery:x']);
assert.equal((await run('ATTACH_RUN_SQL', {id: leased.id, worker_id: 'worker-b', run_id: id(50)})).affectedRows, 0);
assert.equal((await run('ATTACH_RUN_SQL', {id: leased.id, worker_id: 'worker-a', run_id: id(50)})).affectedRows, 1);
await run('ATTACH_RUN_CHECK_SQL', {id: leased.id, run_id: id(50)});
assert.equal((await check(first.id)).run_id, id(50));
assert.equal((await run('ATTACH_RUN_SQL', {id: leased.id, worker_id: 'worker-a', run_id: id(50)})).affectedRows, 0);
assert.equal((await run('STARTED_TODAY_SQL')).rows[0].count, 1);

// Heartbeats extend the lease for its holder only.
assert.equal((await run('HEARTBEAT_SQL', {id: leased.id, worker_id: 'worker-b', completed_calls: 3, lease_seconds: 600})).affectedRows, 0);
assert.equal((await run('HEARTBEAT_SQL', {id: leased.id, worker_id: 'worker-a', completed_calls: 3, lease_seconds: 600})).affectedRows, 1);
assert.equal((await job(first.id)).completed_calls, 3);

// Released for retry: not claimable until its delay passes, then claimable even when the cap is reached.
assert.equal((await run('RELEASE_SQL', {id: leased.id, worker_id: 'worker-a', delay_seconds: 120, error: 'Run ended partial'})).affectedRows, 1);
assert.equal((await job(first.id)).state, 'queued');
assert.equal(await claim('worker-a', false), undefined);
await db.query("update public.visibility_jobs set next_attempt_at=now()-interval '1 second' where id=$1", [leased.id]);
const retried = await claim('worker-a', false);
assert.equal(retried.id, leased.id);
assert.equal(retried.attempt_count, 2);

// Delivery stores the projection and closes the job.
const projection = {schema_version: 'free-check-projection-v1', valid_answers: 15};
assert.equal((await run('COMPLETE_JOB_SQL', {id: leased.id, worker_id: 'worker-a', completed_calls: 15})).affectedRows, 1);
await run('COMPLETE_CHECK_SQL', {id: leased.id, status: 'completed', version: projection.schema_version, projection: JSON.stringify(projection)});
const delivered = await check(first.id);
assert.equal(delivered.status, 'completed');
assert.equal(delivered.error_code, null);
assert.deepEqual(delivered.result_projection, projection);
assert.equal((await job(first.id)).state, 'succeeded');
assert.equal((await run('COMPLETE_JOB_SQL', {id: leased.id, worker_id: 'worker-a', completed_calls: 15})).affectedRows, 0, 'cannot complete twice');

// A partial delivery records why.
const third = await submit(3);
const other = await claim('worker-a');
assert.equal(other.check_id, second.id, 'oldest queued job first');
await run('MARK_RUNNING_SQL', {id: second.id});
await run('COMPLETE_JOB_SQL', {id: other.id, worker_id: 'worker-a', completed_calls: 12});
await run('COMPLETE_CHECK_SQL', {id: other.id, status: 'partial', version: projection.schema_version, projection: JSON.stringify(projection)});
assert.equal((await check(second.id)).error_code, 'some_answers_missing');

// An expired lease is reclaimed by another worker; the old holder can no longer write.
const stuck = await claim('worker-a');
assert.equal(stuck.check_id, third.id);
await run('MARK_RUNNING_SQL', {id: third.id});
assert.equal(await claim('worker-b'), undefined, 'a live lease is not stolen');
await db.query("update public.visibility_jobs set lease_expires_at=now()-interval '1 second' where id=$1", [stuck.id]);
const reclaimed = await claim('worker-b');
assert.equal(reclaimed.id, stuck.id);
assert.equal(reclaimed.lease_owner, 'worker-b');
assert.equal((await run('HEARTBEAT_SQL', {id: stuck.id, worker_id: 'worker-a', completed_calls: 1, lease_seconds: 600})).affectedRows, 0);

// Attempts are bounded: once used up, the job and its check are closed as failed.
await run('RELEASE_SQL', {id: stuck.id, worker_id: 'worker-b', delay_seconds: 0, error: 'RuntimeError'});
await db.query('update public.visibility_jobs set attempt_count=max_attempts where id=$1', [stuck.id]);
assert.equal(await claim('worker-b'), undefined, 'an exhausted job is never claimed');
const closed = (await run('FAIL_EXHAUSTED_SQL')).rows.map(r => r.check_id);
assert.deepEqual(closed, [third.id]);
await run('FAIL_EXHAUSTED_CHECKS_SQL', {ids: closed});
assert.equal((await job(third.id)).state, 'failed');
assert.equal((await job(third.id)).last_error, 'RuntimeError');
const failed = await check(third.id);
assert.equal(failed.status, 'failed');
assert.equal(failed.error_code, 'attempts_exhausted');
assert.equal((await run('FAIL_EXHAUSTED_SQL')).rows.length, 0, 'closing is idempotent');
console.log('free check job queue: all synthetic checks passed');
