// Run with EVIDENCE_SQL_TEST_ENGINE pointing at an isolated @electric-sql/pglite install.
// This creates an in-memory database with synthetic rows only; no Supabase connection.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const { PGlite } = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const db = new PGlite();
await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  alter default privileges in schema public grant all on tables to service_role;
  create table public.business_features (google_place_id text unique);
  create table public.ai_visibility_runs (id uuid primary key, target_google_place_id text);
  insert into public.business_features values ('synthetic-place');
  insert into public.ai_visibility_runs values ('00000000-0000-0000-0000-000000000001', 'synthetic-place');
`);
await db.exec(await readFile('sql/20261001124625_evidence_foundations.sql', 'utf8'));
const tables = ['proposition_catalog', 'proposition_aliases', 'review_profile_metrics', 'ai_measurement_waves'];
// Hosted Supabase grants ALL by default. SELECT/INSERT alone does not revoke those grants.
assert.equal((await db.query("select has_table_privilege('service_role', 'public.review_profile_metrics', 'TRUNCATE') allowed")).rows[0].allowed, true);
await db.exec(await readFile('sql/20261001160431_evidence_foundation_service_permissions.sql', 'utf8'));
for (const table of tables) {
  for (const privilege of ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) {
    const result = await db.query('select has_table_privilege($1, $2, $3) allowed', ['service_role', `public.${table}`, privilege]);
    assert.equal(result.rows[0].allowed, ['SELECT', 'INSERT'].includes(privilege), `${table}: ${privilege}`);
  }
}
const rls = await db.query(`select relname, relrowsecurity from pg_class where relname = any($1::text[])`, [tables]);
assert.equal(rls.rows.length, 4);
assert(rls.rows.every(r => r.relrowsecurity));
const catalogue = await db.query('select count(*)::int n from public.proposition_catalog');
assert.equal(catalogue.rows[0].n, 18);
const alias = await db.query("select proposition_key from public.proposition_aliases where alias_key = 'wedding hair'");
assert.equal(alias.rows[0].proposition_key, 'bridal_hair');

async function reject(sql, pattern) {
  await assert.rejects(db.exec(sql), pattern);
}
for (const role of ['anon', 'authenticated']) {
  await db.exec(`set role ${role}`);
  for (const table of tables) {
    await reject(`select * from public.${table}`, /permission denied/);
    await reject(`delete from public.${table}`, /permission denied/);
  }
  await db.exec('reset role');
}
// RLS still denies rows if someone later accidentally grants client SELECT privileges.
await db.exec('grant select on public.proposition_catalog to anon; set role anon');
assert.equal((await db.query('select * from public.proposition_catalog')).rows.length, 0);
await db.exec('reset role');

const validProfile = `insert into public.review_profile_metrics
  (google_place_id, platform, rating, published_review_count, observed_at, source_record_id, adapter_version, evidence_sha256)
  values ('synthetic-place', 'google', 4.7, 214, '2025-08-05T00:00:00Z', 'source-1', 'adapter-v1', '${'a'.repeat(64)}')`;
await db.exec(validProfile);
await reject(validProfile.replace('214', '-1').replace('source-1', 'source-2'), /check constraint/);
await reject(validProfile.replace('synthetic-place', 'unresolved-place'), /foreign key/);
await reject(validProfile.replace('2025-08-05', '2099-08-05').replace('source-1', 'source-3'), /check constraint/);
await reject('update public.review_profile_metrics set published_review_count=63', /append-only/);
await reject('delete from public.review_profile_metrics', /append-only/);

await db.exec(`insert into public.ai_measurement_waves
  (run_id, series_id, panel_id, panel_kind, configuration_sha256, configuration)
  values ('00000000-0000-0000-0000-000000000001', gen_random_uuid(), '${'b'.repeat(64)}', 'core',
          '${'b'.repeat(64)}', '{"version":"measurement-panel-v1","panel_kind":"core"}')`);
await reject("update public.ai_measurement_waves set panel_kind='focused'", /append-only/);
await reject('delete from public.ai_measurement_waves', /append-only/);
await reject('delete from public.ai_visibility_runs', /foreign key/);
await reject(`insert into public.ai_measurement_waves
  (run_id, series_id, panel_id, panel_kind, configuration_sha256, configuration)
  values (gen_random_uuid(), gen_random_uuid(), '${'b'.repeat(64)}', 'core', '${'b'.repeat(64)}', '{}')`, /check constraint/);
await db.exec('set role service_role');
assert.equal((await db.query('select * from public.review_profile_metrics')).rows.length, 1);
await db.exec(validProfile.replace('source-1', 'source-service'));
assert.equal((await db.query('select * from public.review_profile_metrics')).rows.length, 2);
for (const table of tables) {
  await reject(`delete from public.${table}`, /permission denied/);
  await reject(`truncate public.${table}`, /permission denied/);
}
await db.exec('reset role');
await db.close();
process.stdout.write('PASS: migration, catalogue seed, FK/check constraints, append-only history, client grants/RLS and server access\n');
