-- Increment C: DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Generated with Supabase CLI 2.119.0. Requires A/B. No backfill or report/source changes.
begin;
create table public.positioning_interventions (
    id uuid primary key default gen_random_uuid(),
    action_id uuid not null,
    revision bigint not null check (revision > 0),
    supersedes_id uuid references public.positioning_interventions(id),
    google_place_id text not null references public.business_features(google_place_id),
    proposition_key text not null references public.proposition_catalog(proposition_key),
    capture_id uuid not null,
    baseline_run_id uuid references public.ai_visibility_runs(id),
    baseline_series_id uuid,
    approved_revision_id uuid references public.report_audit_revisions(id),
    approved_action_id text,
    bundle_id uuid,
    record jsonb not null check (jsonb_typeof(record) = 'object'),
    created_by text not null check (length(btrim(created_by)) > 0),
    created_at timestamptz not null default now(),
    foreign key (capture_id,google_place_id) references public.public_evidence_captures(id,google_place_id),
    unique (action_id,revision),
    check ((approved_revision_id is null) = (approved_action_id is null)),
    check (baseline_series_id is null or baseline_run_id is not null)
);
create index positioning_interventions_business_idx on public.positioning_interventions(google_place_id,action_id,revision desc);
create index positioning_interventions_proposition_idx on public.positioning_interventions(proposition_key);
create index positioning_interventions_capture_idx on public.positioning_interventions(capture_id,google_place_id);
create index positioning_interventions_baseline_idx on public.positioning_interventions(baseline_run_id);
create index positioning_interventions_approved_idx on public.positioning_interventions(approved_revision_id);
create index positioning_interventions_supersedes_idx on public.positioning_interventions(supersedes_id);
create index positioning_interventions_bundle_idx on public.positioning_interventions(bundle_id);

create function public.validate_positioning_intervention() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare
    previous public.positioning_interventions;
    c public.public_evidence_captures;
    value jsonb;
    field text;
begin
    perform pg_advisory_xact_lock(hashtextextended('intervention:' || NEW.action_id::text,0));
    select * into previous from public.positioning_interventions where action_id=NEW.action_id order by revision desc limit 1;
    if previous.id is null then
        if NEW.revision<>1 or NEW.supersedes_id is not null then raise exception 'First action revision must be 1 with no predecessor'; end if;
    elsif NEW.revision<>previous.revision+1 or NEW.supersedes_id is distinct from previous.id
       or NEW.google_place_id<>previous.google_place_id or NEW.proposition_key<>previous.proposition_key or NEW.capture_id<>previous.capture_id then
        raise exception 'Action revisions must append to the same business, proposition and capture';
    end if;
    if not (NEW.record ?& array['version','action_id','google_place_id','proposition_key','capture_id','finding','hypothesis','owner','priority','effort','status','created_by','revision_note','affected_evidence_ids','finding_snapshot','completion_evidence','planned_date','implemented_date','focused_families','baseline_run_id','baseline_series_id','approved_revision_id','approved_action_id','bundle_id'])
       or NEW.record->>'version' is distinct from 'intervention-v1'
       or NEW.record->>'action_id' is distinct from NEW.action_id::text
       or NEW.record->>'google_place_id' is distinct from NEW.google_place_id
       or NEW.record->>'proposition_key' is distinct from NEW.proposition_key
       or NEW.record->>'capture_id' is distinct from NEW.capture_id::text
       or NEW.record->>'created_by' is distinct from NEW.created_by
       or NEW.record->>'baseline_run_id' is distinct from NEW.baseline_run_id::text
       or NEW.record->>'baseline_series_id' is distinct from NEW.baseline_series_id::text
       or NEW.record->>'approved_revision_id' is distinct from NEW.approved_revision_id::text
       or NEW.record->>'approved_action_id' is distinct from NEW.approved_action_id
       or NEW.record->>'bundle_id' is distinct from NEW.bundle_id::text then
        raise exception 'Action record and relational identity must match';
    end if;
    foreach field in array array['finding','hypothesis','owner','effort','created_by','revision_note'] loop
        if jsonb_typeof(NEW.record->field) is distinct from 'string' or length(btrim(NEW.record->>field))=0 then
            raise exception 'Action requires explained finding, hypothesis, owner, effort, operator and revision note';
        end if;
    end loop;
    if coalesce(NEW.record->>'status','') not in ('PLANNED','IN_PROGRESS','IMPLEMENTED','PAUSED','CANCELLED')
       or coalesce(NEW.record->>'priority','') not in ('Not yet agreed','High','Medium','Low') then
        raise exception 'Invalid action status or priority';
    end if;
    foreach field in array array['affected_evidence_ids','completion_evidence','focused_families'] loop
        if jsonb_typeof(NEW.record->field) is distinct from 'array' then raise exception 'Action lists must be arrays'; end if;
        if exists (select 1 from jsonb_array_elements(NEW.record->field) e where jsonb_typeof(e.value)<>'string' or length(btrim(e.value#>>'{}'))=0)
           or (select count(*) from jsonb_array_elements(NEW.record->field))<>(select count(distinct e.value) from jsonb_array_elements(NEW.record->field) e) then
            raise exception 'Action lists require distinct nonblank strings';
        end if;
    end loop;
    if jsonb_array_length(NEW.record->'affected_evidence_ids')=0 then raise exception 'Affected evidence is required'; end if;
    for value in select e.value from jsonb_array_elements(NEW.record->'affected_evidence_ids') e loop
        if not exists (select 1 from public.public_evidence_observations o where o.capture_id=NEW.capture_id and o.evidence_id=value#>>'{}') then
            raise exception 'Affected evidence must belong to the exact capture';
        end if;
    end loop;
    select * into strict c from public.public_evidence_captures where id=NEW.capture_id;
    if jsonb_typeof(NEW.record->'finding_snapshot') is distinct from 'object'
       or NEW.record->'finding_snapshot'->>'capture_id' is distinct from NEW.capture_id::text
       or NEW.record->'finding_snapshot'->>'capture_sha256' is distinct from c.payload_sha256
       or NEW.record->'finding_snapshot'->>'google_place_id' is distinct from NEW.google_place_id
       or jsonb_typeof(NEW.record->'finding_snapshot'->'rows') is distinct from 'array' then
        raise exception 'Finding snapshot must identify the immutable capture';
    end if;
    if not exists (select 1 from jsonb_array_elements(NEW.record->'finding_snapshot'->'rows') r where r.value->>'proposition_key'=NEW.proposition_key) then
        raise exception 'Finding snapshot must include the action proposition';
    end if;
    if NEW.baseline_run_id is not null and not exists (select 1 from public.ai_visibility_runs r where r.id=NEW.baseline_run_id and r.target_google_place_id=NEW.google_place_id) then
        raise exception 'Baseline run must belong to the action business';
    end if;
    if NEW.baseline_series_id is not null and not exists (select 1 from public.ai_measurement_waves w where w.run_id=NEW.baseline_run_id and w.series_id=NEW.baseline_series_id) then
        raise exception 'Baseline series must identify the exact baseline wave';
    end if;
    if NEW.approved_revision_id is not null and not exists (
        select 1 from public.report_audit_revisions r,
        lateral jsonb_array_elements(coalesce(r.reviewer_decisions->'approved_recommendations','[]'::jsonb)) a
        where r.id=NEW.approved_revision_id and r.target_google_place_id=NEW.google_place_id
          and r.reviewer_decisions_complete and a.value->>'id'=NEW.approved_action_id
    ) then raise exception 'Approved action must exist in its completed same-business report revision'; end if;
    if NEW.bundle_id is not null then
        perform pg_advisory_xact_lock(hashtextextended('intervention-bundle:' || NEW.bundle_id::text,0));
        if exists (select 1 from public.positioning_interventions where bundle_id=NEW.bundle_id and google_place_id<>NEW.google_place_id) then
            raise exception 'Action bundle must belong to one business';
        end if;
    end if;
    foreach field in array array['planned_date','implemented_date'] loop
        if NEW.record->>field is not null then
            if jsonb_typeof(NEW.record->field)<>'string' or NEW.record->>field !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'Action dates require YYYY-MM-DD'; end if;
            perform (NEW.record->>field)::date;
        end if;
    end loop;
    if (NEW.record->>'implemented_date')::date > current_date then raise exception 'Implementation cannot be in the future'; end if;
    if ((NEW.record->>'implemented_date') is null)<>(jsonb_array_length(NEW.record->'completion_evidence')=0)
       or (NEW.record->>'status'='IMPLEMENTED' and NEW.record->>'implemented_date' is null) then
        raise exception 'Implemented action requires an actual date and completion evidence';
    end if;
    if exists (select 1 from jsonb_array_elements_text(NEW.record->'completion_evidence') e where e.value !~* '^https?://[^[:space:]@]+$') then
        raise exception 'Completion evidence requires public URLs';
    end if;
    return NEW;
end;
$$;
create trigger validate_positioning_interventions before insert on public.positioning_interventions
    for each row execute function public.validate_positioning_intervention();
create trigger immutable_positioning_interventions before update or delete on public.positioning_interventions
    for each row execute function public.reject_evidence_foundation_change();
revoke all on function public.validate_positioning_intervention() from public,anon,authenticated;
grant execute on function public.validate_positioning_intervention() to service_role;
alter table public.positioning_interventions enable row level security;
revoke all on public.positioning_interventions from public,anon,authenticated,service_role;
grant select,insert on public.positioning_interventions to service_role;
commit;
