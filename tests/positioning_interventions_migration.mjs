// Synthetic in-memory PostgreSQL only. No production connection or rows.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {PGlite} = await import(pathToFileURL(process.env.EVIDENCE_SQL_TEST_ENGINE).href);
const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
alter default privileges in schema public grant all on tables to service_role;
create table public.business_features(google_place_id text unique);
create table public.ai_visibility_runs(id uuid primary key,target_google_place_id text);
create table public.report_audit_revisions(id uuid primary key,target_google_place_id text,reviewer_decisions jsonb,reviewer_decisions_complete boolean);
grant select on public.ai_visibility_runs,public.report_audit_revisions to service_role;
insert into public.business_features values ('place'),('other');`);
for (const file of ['20261001124625_evidence_foundations.sql','20261001160431_evidence_foundation_service_permissions.sql','20261001174111_public_evidence_archive.sql','20261002085635_positioning_interventions.sql']) {
    await db.exec(await readFile(`sql/${file}`,'utf8'));
}
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
const observation = {evidence_id:'excerpt',kind:'proposition_candidate',field:'balayage',source_class:'website',source_record_id:'page',google_place_id:'place',raw_value:'We offer balayage.'};
const payload = {version:'public-evidence-capture-v1',google_place_id:'place',source_bundle:{},matrix:{observations:[observation]},catalogue:[],aliases:[]};
const body=JSON.stringify(payload),hash=createHash('sha256').update(body).digest('hex');
await db.query(`insert into public.public_evidence_captures(id,google_place_id,capture_version,payload,canonical_payload,payload_sha256,archived_by)
values($1,'place','public-evidence-capture-v1',$2::text::jsonb,$2::text,$3,'Synthetic operator')`,[id(1),body,hash]);
await db.query('insert into public.public_evidence_observations(capture_id,evidence_id,observation) values($1,$2,$3::jsonb)',[id(1),'excerpt',JSON.stringify(observation)]);
await db.query("insert into public.ai_visibility_runs values ($1,'place'),($2,'other')",[id(2),id(3)]);
await db.query("insert into public.report_audit_revisions values($1,'place',$2,true),($3,'other',$2,true)",[id(4),JSON.stringify({approved_recommendations:[{id:'approved-1'}]}),id(5)]);
await db.query(`insert into public.ai_measurement_waves(run_id,series_id,panel_id,panel_kind,configuration_sha256,configuration)
values($1,$2,$3,'core',$3,'{"version":"measurement-panel-v1","panel_kind":"core"}')`,[id(2),id(6),'a'.repeat(64)]);
const record = {version:'intervention-v1',action_id:id(10),google_place_id:'place',proposition_key:'balayage',capture_id:id(1),
finding:'Saved evidence needs review',hypothesis:'Investigate before changing the page',owner:'Owner',priority:'Not yet agreed',effort:'Not yet estimated',
status:'PLANNED',created_by:'Operator',revision_note:'Initial proposed investigation',affected_evidence_ids:['excerpt'],focused_families:[],
planned_date:null,implemented_date:null,completion_evidence:[],baseline_run_id:id(2),baseline_series_id:id(6),
approved_revision_id:id(4),approved_action_id:'approved-1',bundle_id:id(7),
finding_snapshot:{google_place_id:'place',capture_id:id(1),capture_sha256:hash,rows:[{proposition_key:'balayage'}]}};
const insert = `insert into public.positioning_interventions(id,action_id,revision,supersedes_id,google_place_id,proposition_key,capture_id,
baseline_run_id,baseline_series_id,approved_revision_id,approved_action_id,bundle_id,record,created_by)
values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14)`;
const params=(r,revision=1,predecessor=null,rowid=id(11)) => [rowid,r.action_id,revision,predecessor,r.google_place_id,r.proposition_key,r.capture_id,
r.baseline_run_id,r.baseline_series_id,r.approved_revision_id,r.approved_action_id,r.bundle_id,JSON.stringify(r),r.created_by];
await db.exec('set role service_role');
await db.query(insert,params(record));
assert.equal((await db.query('select count(*)::int n from public.positioning_interventions')).rows[0].n,1);
for (const [change,pattern] of [
 [{capture_id:id(99)},/strict|no rows|capture|foreign key/i],
 [{google_place_id:'other'},/capture|foreign key|snapshot/i],
 [{affected_evidence_ids:['forged']},/exact capture/i],
 [{affected_evidence_ids:[]},/required/i],
 [{affected_evidence_ids:[null]},/nonblank/i],
 [{finding_snapshot:null},/snapshot/i],
 [{finding_snapshot:{google_place_id:'place',capture_id:id(1),capture_sha256:'forged',rows:[]}},/snapshot/i],
 [{status:'IMPLEMENTED'},/actual date/i],
 [{implemented_date:'2099-01-01',completion_evidence:['https://example.org/proof']},/future/i],
 [{implemented_date:'2026-01-01',completion_evidence:['file:///private/proof']},/public URLs/i],
 [{baseline_run_id:id(3),baseline_series_id:null},/business/i],
 [{baseline_series_id:id(99)},/exact baseline/i],
 [{approved_action_id:'invented'},/completed same-business/i],
 [{approved_revision_id:id(5)},/same-business/i],
 [{focused_families:['same','same']},/distinct/i],
 [{finding:null},/requires explained/i],
 [{planned_date:17},/YYYY-MM-DD/i],
]) {
    const invalid={...record,...change,action_id:id(20)};
    await assert.rejects(db.query(insert,params(invalid,1,null,id(21))),pattern);
}
await assert.rejects(db.query(insert,params({...record,action_id:id(20)},2,null,id(21))),/First action revision/);
await assert.rejects(db.query(insert,params(record,2,null,id(21))),/must append/);
await assert.rejects(db.query(insert,params({...record,proposition_key:'bridal_hair'},2,id(11),id(21))),/same business, proposition and capture/);
const completed={...record,status:'IMPLEMENTED',implemented_date:'2026-01-01',completion_evidence:['https://example.org/proof'],revision_note:'Owner supplied completion proof'};
await db.query(insert,params(completed,2,id(11),id(12)));
assert.equal((await db.query('select count(*)::int n from public.positioning_interventions')).rows[0].n,2);
for (const privilege of ['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','TRIGGER','REFERENCES']) {
 assert.equal((await db.query("select has_table_privilege('service_role','public.positioning_interventions',$1) p",[privilege])).rows[0].p,['SELECT','INSERT'].includes(privilege));
}
await assert.rejects(db.exec('delete from public.positioning_interventions'),/permission denied/);
await assert.rejects(db.exec('truncate public.positioning_interventions'),/permission denied/);
await db.exec('reset role');
await assert.rejects(db.exec('update public.positioning_interventions set created_by=created_by'),/append-only/);
for (const role of ['anon','authenticated']) {
 await db.exec(`set role ${role}`);
 await assert.rejects(db.exec('select * from public.positioning_interventions'),/permission denied/);
 await db.exec('reset role');
}
await db.exec('grant select on public.positioning_interventions to anon; set role anon');
assert.equal((await db.query('select * from public.positioning_interventions')).rows.length,0);
await db.close();
process.stdout.write('PASS: C schema, same-business evidence/baselines/approved actions, revision chain, completion proof, immutable history and hosted-default grants/RLS\n');
