begin;

create table public.poc_audit_snapshots (
    id uuid primary key,
    schema_version text not null,
    ai_run_id uuid not null,
    snapshot_revision integer not null,
    supersedes_snapshot_id uuid,
    revision_reason text not null,
    target_google_place_id text not null,
    target_business_name text not null,
    audit_date date not null,
    report_payload jsonb not null,
    report_payload_sha256 text not null,
    pdf_bytes bytea not null,
    pdf_sha256 text not null,
    pdf_filename text not null,
    pdf_mime_type text not null default 'application/pdf',
    frozen_by text not null,
    frozen_at timestamptz not null default now(),

    constraint poc_audit_snapshots_ai_run_fk
        foreign key (ai_run_id)
        references public.ai_visibility_runs (id)
        on update restrict
        on delete restrict,

    constraint poc_audit_snapshots_schema_version_check
        check (schema_version = 'poc_audit_v1'),
    constraint poc_audit_snapshots_revision_check
        check (snapshot_revision >= 1),
    constraint poc_audit_snapshots_revision_reason_check
        check (btrim(revision_reason) <> ''),
    constraint poc_audit_snapshots_revision_shape_check
        check (
            (snapshot_revision = 1 and supersedes_snapshot_id is null)
            or
            (snapshot_revision > 1 and supersedes_snapshot_id is not null)
        ),
    constraint poc_audit_snapshots_target_check
        check (
            btrim(target_google_place_id) <> ''
            and target_google_place_id not like 'discovery:%'
        ),
    constraint poc_audit_snapshots_target_name_check
        check (btrim(target_business_name) <> ''),
    constraint poc_audit_snapshots_payload_object_check
        check (jsonb_typeof(report_payload) = 'object'),
    constraint poc_audit_snapshots_payload_schema_check
        check (
            report_payload ->> 'schema_version'
                is not distinct from schema_version
        ),
    constraint poc_audit_snapshots_payload_run_check
        check (
            report_payload #>> '{audit,baseline_run_id}'
                is not distinct from ai_run_id::text
        ),
    constraint poc_audit_snapshots_payload_target_check
        check (
            report_payload #>> '{audit,target_google_place_id}'
                is not distinct from target_google_place_id
        ),
    constraint poc_audit_snapshots_payload_target_name_check
        check (
            report_payload #>> '{audit,target_business_name}'
                is not distinct from target_business_name
        ),
    constraint poc_audit_snapshots_payload_audit_date_check
        check (
            report_payload #>> '{audit,audit_date}'
                is not distinct from audit_date::text
        ),
    constraint poc_audit_snapshots_payload_revision_check
        check (
            (report_payload #>> '{revision,snapshot_revision}')::integer
                is not distinct from snapshot_revision
        ),
    constraint poc_audit_snapshots_payload_supersedes_check
        check (
            nullif(
                report_payload #>> '{revision,supersedes_snapshot_id}',
                ''
            ) is not distinct from supersedes_snapshot_id::text
        ),
    constraint poc_audit_snapshots_payload_reason_check
        check (
            report_payload #>> '{revision,revision_reason}'
                is not distinct from revision_reason
        ),
    constraint poc_audit_snapshots_payload_hash_check
        check (report_payload_sha256 ~ '^[0-9a-f]{64}$'),
    constraint poc_audit_snapshots_pdf_hash_check
        check (pdf_sha256 ~ '^[0-9a-f]{64}$'),
    constraint poc_audit_snapshots_pdf_bytes_check
        check (octet_length(pdf_bytes) > 0),
    constraint poc_audit_snapshots_pdf_filename_check
        check (btrim(pdf_filename) <> ''),
    constraint poc_audit_snapshots_pdf_mime_check
        check (pdf_mime_type = 'application/pdf'),
    constraint poc_audit_snapshots_frozen_by_check
        check (btrim(frozen_by) <> ''),

    constraint poc_audit_snapshots_run_revision_key
        unique (ai_run_id, snapshot_revision),
    constraint poc_audit_snapshots_id_run_key
        unique (id, ai_run_id),
    constraint poc_audit_snapshots_supersedes_same_run_fk
        foreign key (supersedes_snapshot_id, ai_run_id)
        references public.poc_audit_snapshots (id, ai_run_id)
        on update restrict
        on delete restrict
);

create index poc_audit_snapshots_target_frozen_idx
    on public.poc_audit_snapshots (
        target_google_place_id,
        frozen_at desc
    );

create index poc_audit_snapshots_supersedes_idx
    on public.poc_audit_snapshots (supersedes_snapshot_id)
    where supersedes_snapshot_id is not null;

create function public.enforce_poc_audit_snapshot_lineage()
returns trigger
language plpgsql
as $$
declare
    latest_snapshot_id uuid;
    latest_revision integer;
begin
    perform pg_advisory_xact_lock(
        hashtextextended(new.ai_run_id::text, 0)
    );

    select id, snapshot_revision
    into latest_snapshot_id, latest_revision
    from public.poc_audit_snapshots
    where ai_run_id = new.ai_run_id
    order by snapshot_revision desc
    limit 1;

    if latest_revision is null then
        if new.snapshot_revision <> 1
            or new.supersedes_snapshot_id is not null then
            raise exception
                'First POC audit snapshot for run % must be revision 1',
                new.ai_run_id;
        end if;
    elsif new.snapshot_revision <> latest_revision + 1 then
        raise exception
            'POC audit snapshot revision % must follow revision % for run %',
            new.snapshot_revision,
            latest_revision,
            new.ai_run_id;
    elsif new.supersedes_snapshot_id is distinct from latest_snapshot_id then
        raise exception
            'POC audit snapshot revision % must supersede snapshot %',
            new.snapshot_revision,
            latest_snapshot_id;
    end if;

    return new;
end;
$$;

create trigger poc_audit_snapshots_lineage_before_insert
before insert on public.poc_audit_snapshots
for each row
execute function public.enforce_poc_audit_snapshot_lineage();

create function public.prevent_poc_audit_snapshot_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'POC audit snapshots are immutable';
end;
$$;

create trigger poc_audit_snapshots_immutable_before_change
before update or delete on public.poc_audit_snapshots
for each row
execute function public.prevent_poc_audit_snapshot_mutation();

commit;
