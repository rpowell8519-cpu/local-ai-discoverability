// Synthetic PostgreSQL validation only. No production connection or rows.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const { PGlite } = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
  alter default privileges in schema public grant all on tables to service_role;
  create table public.business_features(google_place_id text unique);
  create table public.ai_visibility_runs(id uuid primary key);
  insert into public.business_features values ('synthetic-place'),('other-place');`);
for (const file of ['20261001124625_evidence_foundations.sql', '20261001160431_evidence_foundation_service_permissions.sql', '20261001174111_public_evidence_archive.sql']) {
  await db.exec(await readFile(`sql/${file}`, 'utf8'));
}
const tables = ['public_evidence_captures', 'public_evidence_observations', 'public_evidence_decisions', 'public_evidence_collection_attempts'];
assert.equal((await db.query('select count(*)::int n from pg_class where relname=any($1::text[]) and relrowsecurity', [tables])).rows[0].n, 4);
for (const table of tables) {
  for (const privilege of ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','TRIGGER','REFERENCES']) {
    const grants = await db.query('select has_table_privilege($1,$2,$3) permitted', ['service_role', `public.${table}`, privilege]);
    assert.equal(grants.rows[0].permitted, ['SELECT','INSERT'].includes(privilege), `${table}: ${privilege}`);
  }
}
async function reject(sql, params, pattern) { await assert.rejects(db.query(sql, params), pattern); }
const capid = '00000000-0000-0000-0000-000000000001';
const prop = {evidence_id:'excerpt-1',kind:'proposition_candidate',field:'balayage',source_class:'website',source_record_id:'page-1',google_place_id:'synthetic-place',raw_value:'We offer balayage.'};
const fact = {evidence_id:'fact-1',kind:'fact',field:'phone',source_class:'google_profile',source_record_id:'listing-1',google_place_id:'synthetic-place',raw_value:'01273 123456'};
const payload = {version:'public-evidence-capture-v1',google_place_id:'synthetic-place',source_bundle:{saved:'primary context'},matrix:{observations:[prop,fact]},catalogue:[],aliases:[]};
const body = JSON.stringify(payload);
const hash = createHash('sha256').update(body).digest('hex');
const capsql = `insert into public.public_evidence_captures(id,google_place_id,capture_version,payload,canonical_payload,payload_sha256,archived_by)
  values($1,'synthetic-place','public-evidence-capture-v1',$2::text::jsonb,$2::text,$3,'Operator')`;
await db.exec('set role service_role');
await db.query(capsql,[capid,body,hash]);
assert.equal((await db.query('select canonical_payload from public.public_evidence_captures')).rows[0].canonical_payload,body);
await reject(capsql,['00000000-0000-0000-0000-000000000002',body,'0'.repeat(64)],/check constraint/);
const obsSql = 'insert into public.public_evidence_observations(capture_id,evidence_id,observation) values($1,$2,$3::jsonb)';
await db.query(obsSql,[capid,prop.evidence_id,JSON.stringify(prop)]);
await db.query(obsSql,[capid,fact.evidence_id,JSON.stringify(fact)]);
await reject(obsSql,[capid,'forged-excerpt',JSON.stringify({...prop,evidence_id:'forged-excerpt',raw_value:'Invented expertise'})],/exactly match/);
const decisionSql = `insert into public.public_evidence_decisions(capture_id,evidence_id,revision,decision,origin,identity_confirmed,reviewer,note)
  values($1,$2,$3,$4,$5,$6,'Operator','Checked exact source context')`;
await db.query(decisionSql,[capid,prop.evidence_id,1,'EXPLICIT_SUPPORT','owner_claim',true]);
await db.query(decisionSql,[capid,prop.evidence_id,2,'UNCERTAIN','unknown',false]);
await reject(decisionSql,[capid,prop.evidence_id,3,'EXPLICIT_SUPPORT','unknown',false],/check constraint/);
await reject(decisionSql,[capid,fact.evidence_id,1,'EXPLICIT_SUPPORT','owner_claim',true],/foreign key/);
await reject(decisionSql,[capid,'missing-excerpt',1,'EXPLICIT_SUPPORT','owner_claim',true],/foreign key/);
assert.equal((await db.query('select count(*)::int n from public.public_evidence_decisions')).rows[0].n,2);
const attemptSql = `insert into public.public_evidence_collection_attempts
  (google_place_id,source_class,source_url,status,observed_at,sample_size,scope,note,adapter_version,capture_id)
  values($1,'yelp_reviews','https://yelp.example/profile',$2,$3,$4,'Profile review text','Explained outcome','manual-v1',$5)`;
await db.query(attemptSql,['synthetic-place','CHECKED_EMPTY','2025-08-05T00:00:00Z',0,capid]);
await db.query(attemptSql,['synthetic-place','FAILED','2025-08-05T00:00:00Z',null,null]);
await reject(attemptSql,['synthetic-place','FAILED','2025-08-05T00:00:00Z',0,null],/check constraint/);
await reject(attemptSql,['synthetic-place','NOT_CHECKED','2025-08-05T00:00:00Z',null,null],/check constraint/);
await reject(attemptSql,['synthetic-place','COLLECTED','2099-08-05T00:00:00Z',63,null],/check constraint/);
await reject(attemptSql,['other-place','CHECKED_EMPTY','2025-08-05T00:00:00Z',0,capid],/foreign key/);
for (const table of tables) {
  await reject(`delete from public.${table}`,[],/permission denied/);
  await reject(`truncate public.${table}`,[],/permission denied/);
}
await db.exec('reset role');
for (const table of tables) await reject(`delete from public.${table}`,[],/append-only/);
await reject("update public.public_evidence_decisions set decision='NO_SUPPORT'",[],/append-only/);
for (const role of ['anon','authenticated']) {
  await db.exec(`set role ${role}`);
  for (const table of tables) await reject(`select * from public.${table}`,[],/permission denied/);
  await db.exec('reset role');
}
await db.exec('grant select on public.public_evidence_captures to anon; set role anon');
assert.equal((await db.query('select * from public.public_evidence_captures')).rows.length,0);
await db.exec('reset role');
await db.close();
process.stdout.write('PASS: archive SQL, payload hash, captured-observation integrity, decision FKs/history, attempt outcomes, immutability and hosted-default grants/RLS\n');
