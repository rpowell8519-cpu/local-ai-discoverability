-- Durable, immutable report setup and review state.
-- Lifecycle stage is derived by the application from these recorded facts.

begin;

create table public.report_audit_revisions (
    id uuid primary key,
    schema_version text not null,
    target_google_place_id text not null,
    target_business_name text not null,
    revision integer not null,
    supersedes_revision_id uuid,
    revision_reason text not null,
    known_for text not null,
    desired_searches jsonb not null,
    owner_competitors jsonb not null default '[]'::jsonb,
    benchmark_run_id uuid,
    website_evidence_state text not null default 'not_checked',
    review_evidence_state text not null default 'not_checked',
    reviewer_decisions jsonb not null default '{}'::jsonb,
    reviewer_decisions_complete boolean not null default false,
    created_by text not null,
    created_at timestamptz not null default now(),

    constraint report_audit_revisions_schema_check
        check (schema_version = 'report_audit_workflow_v1'),
    constraint report_audit_revisions_target_fk
        foreign key (target_google_place_id)
        references public.business_features (google_place_id)
        on update restrict on delete restrict,
    constraint report_audit_revisions_benchmark_fk
        foreign key (benchmark_run_id)
        references public.ai_visibility_runs (id)
        on update restrict on delete restrict,
    constraint report_audit_revisions_revision_check check (revision >= 1),
    constraint report_audit_revisions_shape_check check (
        (revision = 1 and supersedes_revision_id is null)
        or (revision > 1 and supersedes_revision_id is not null)
    ),
    constraint report_audit_revisions_target_check check (
        btrim(target_google_place_id) <> ''
        and target_google_place_id not like 'discovery:%'
    ),
    constraint report_audit_revisions_name_check
        check (btrim(target_business_name) <> ''),
    constraint report_audit_revisions_reason_check
        check (btrim(revision_reason) <> ''),
    constraint report_audit_revisions_known_for_check
        check (length(btrim(known_for)) >= 10),
    constraint report_audit_revisions_searches_check check (
        jsonb_typeof(desired_searches) = 'array'
        and jsonb_array_length(desired_searches) >= 1
    ),
    constraint report_audit_revisions_competitors_check
        check (jsonb_typeof(owner_competitors) = 'array'),
    constraint report_audit_revisions_website_state_check check (
        website_evidence_state in ('available', 'unavailable', 'not_checked')
    ),
    constraint report_audit_revisions_review_state_check check (
        review_evidence_state in ('available', 'unavailable', 'not_checked')
    ),
    constraint report_audit_revisions_decisions_check
        check (jsonb_typeof(reviewer_decisions) = 'object'),
    constraint report_audit_revisions_created_by_check
        check (btrim(created_by) <> ''),
    constraint report_audit_revisions_place_revision_key
        unique (target_google_place_id, revision),
    constraint report_audit_revisions_id_place_key
        unique (id, target_google_place_id),
    constraint report_audit_revisions_supersedes_fk
        foreign key (supersedes_revision_id, target_google_place_id)
        references public.report_audit_revisions (id, target_google_place_id)
        on update restrict on delete restrict
);

create index report_audit_revisions_latest_idx
    on public.report_audit_revisions (target_google_place_id, revision desc);

create function public.enforce_report_audit_revision_lineage()
returns trigger language plpgsql as $$
declare
    latest_id uuid;
    latest_revision integer;
begin
    perform pg_advisory_xact_lock(
        hashtextextended(new.target_google_place_id, 0)
    );
    select id, revision into latest_id, latest_revision
    from public.report_audit_revisions
    where target_google_place_id = new.target_google_place_id
    order by revision desc limit 1;

    if latest_revision is null then
        if new.revision <> 1 or new.supersedes_revision_id is not null then
            raise exception 'First report audit revision must be revision 1';
        end if;
    elsif new.revision <> latest_revision + 1
        or new.supersedes_revision_id is distinct from latest_id then
        raise exception 'Report audit revision does not follow the latest revision';
    end if;
    return new;
end;
$$;

create trigger report_audit_revisions_lineage_before_insert
before insert on public.report_audit_revisions
for each row execute function public.enforce_report_audit_revision_lineage();

create function public.prevent_report_audit_revision_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'Report audit revisions are immutable';
end;
$$;

create trigger report_audit_revisions_immutable_before_change
before update or delete on public.report_audit_revisions
for each row execute function public.prevent_report_audit_revision_mutation();

revoke all privileges on table public.report_audit_revisions
from anon, authenticated;

alter table public.report_audit_revisions enable row level security;

commit;
