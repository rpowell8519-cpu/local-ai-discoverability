-- Increment B: DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires applied Increment A. No historical source records or issued snapshots are changed.
begin;
create table public.public_evidence_captures (
    id uuid primary key default gen_random_uuid(),
    google_place_id text not null references public.business_features(google_place_id),
    capture_version text not null check (capture_version = 'public-evidence-capture-v1'),
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    canonical_payload text not null check (canonical_payload::jsonb = payload),
    payload_sha256 text not null check (payload_sha256 = encode(sha256(convert_to(canonical_payload, 'UTF8')), 'hex')),
    archived_by text not null check (length(btrim(archived_by)) > 0),
    archived_at timestamptz not null default now() check (archived_at <= now()),
    check (payload ?& array['version','google_place_id','source_bundle','matrix','catalogue','aliases']),
    check (payload->'version' = to_jsonb(capture_version) and payload->'google_place_id' = to_jsonb(google_place_id)),
    check (jsonb_typeof(payload->'matrix') = 'object' and (payload->'matrix') ? 'observations'),
    check (jsonb_typeof(payload->'matrix'->'observations') = 'array'),
    unique (google_place_id, payload_sha256),
    unique (id, google_place_id)
);
create index public_evidence_captures_business_time_idx on public.public_evidence_captures(google_place_id, archived_at desc, id desc);

create table public.public_evidence_observations (
    capture_id uuid not null references public.public_evidence_captures(id),
    evidence_id text not null,
    observation jsonb not null check (jsonb_typeof(observation) = 'object'),
    kind text generated always as (observation->>'kind') stored not null,
    proposition_key text generated always as (case when observation->>'kind' = 'proposition_candidate' then observation->>'field' end) stored
        references public.proposition_catalog(proposition_key),
    check (observation ?& array['evidence_id','kind','field','source_class','source_record_id','google_place_id']),
    check (kind in ('fact','proposition_candidate')),
    check (observation->'evidence_id' = to_jsonb(evidence_id)),
    check (coalesce(length(btrim(observation->>'field')),0) > 0
        and coalesce(length(btrim(observation->>'source_class')),0) > 0
        and coalesce(length(btrim(observation->>'source_record_id')),0) > 0),
    primary key (capture_id, evidence_id),
    unique (capture_id, evidence_id, kind)
);
create index public_evidence_observations_proposition_idx on public.public_evidence_observations(proposition_key);

create table public.public_evidence_decisions (
    id uuid primary key default gen_random_uuid(),
    capture_id uuid not null,
    evidence_id text not null,
    observation_kind text not null default 'proposition_candidate' check (observation_kind = 'proposition_candidate'),
    revision bigint not null check (revision > 0),
    decision text not null check (decision in ('UNCERTAIN','NO_SUPPORT','EXPLICIT_SUPPORT','IMPLICIT_SUPPORT','CONTRADICTS')),
    origin text not null check (origin in ('unknown','owner_claim','customer_report','independent_third_party','syndicated_claim')),
    identity_confirmed boolean not null,
    reviewer text not null check (length(btrim(reviewer)) > 0),
    note text not null check (length(btrim(note)) > 0),
    created_at timestamptz not null default now() check (created_at <= now()),
    check (decision in ('UNCERTAIN','NO_SUPPORT') or (identity_confirmed and origin <> 'unknown')),
    foreign key (capture_id,evidence_id,observation_kind) references public.public_evidence_observations(capture_id,evidence_id,kind),
    unique (capture_id,evidence_id,revision)
);
create index public_evidence_decisions_observation_idx on public.public_evidence_decisions(capture_id,evidence_id,observation_kind);

create table public.public_evidence_collection_attempts (
    id uuid primary key default gen_random_uuid(),
    google_place_id text not null references public.business_features(google_place_id),
    source_class text not null check (length(btrim(source_class)) > 0),
    source_url text not null check (source_url ~* '^https?://[^[:space:]]+$'),
    status text not null check (status in ('COLLECTED','CHECKED_EMPTY','FAILED','UNAVAILABLE')),
    observed_at timestamptz not null check (observed_at <= now()),
    sample_size integer,
    scope text not null check (length(btrim(scope)) > 0),
    note text not null check (length(btrim(note)) > 0),
    adapter_version text not null check (length(btrim(adapter_version)) > 0),
    capture_id uuid,
    created_at timestamptz not null default now(),
    foreign key (capture_id,google_place_id) references public.public_evidence_captures(id,google_place_id),
    check ((status='COLLECTED' and sample_size is not null and sample_size > 0)
        or (status='CHECKED_EMPTY' and sample_size is not null and sample_size=0)
        or (status in ('FAILED','UNAVAILABLE') and sample_size is null))
);
create index public_evidence_attempts_business_time_idx on public.public_evidence_collection_attempts(google_place_id,observed_at desc,id desc);
create index public_evidence_attempts_capture_business_idx on public.public_evidence_collection_attempts(capture_id,google_place_id);

create function public.validate_archived_evidence_observation() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if not exists (
        select 1 from public.public_evidence_captures c,
        lateral jsonb_array_elements(c.payload->'matrix'->'observations') o
        where c.id=NEW.capture_id and o.value=NEW.observation
          and c.google_place_id=NEW.observation->>'google_place_id'
    ) then
        raise exception 'Observation must exactly match the immutable capture';
    end if;
    return NEW;
end;
$$;
create trigger public_evidence_observation_matches_capture before insert on public.public_evidence_observations
    for each row execute function public.validate_archived_evidence_observation();
revoke all on function public.validate_archived_evidence_observation() from public,anon,authenticated;
grant execute on function public.validate_archived_evidence_observation() to service_role;

create trigger immutable_public_evidence_captures before update or delete on public.public_evidence_captures
    for each row execute function public.reject_evidence_foundation_change();
create trigger immutable_public_evidence_observations before update or delete on public.public_evidence_observations
    for each row execute function public.reject_evidence_foundation_change();
create trigger immutable_public_evidence_decisions before update or delete on public.public_evidence_decisions
    for each row execute function public.reject_evidence_foundation_change();
create trigger immutable_public_evidence_attempts before update or delete on public.public_evidence_collection_attempts
    for each row execute function public.reject_evidence_foundation_change();

alter table public.public_evidence_captures enable row level security;
alter table public.public_evidence_observations enable row level security;
alter table public.public_evidence_decisions enable row level security;
alter table public.public_evidence_collection_attempts enable row level security;
revoke all on public.public_evidence_captures,public.public_evidence_observations,
    public.public_evidence_decisions,public.public_evidence_collection_attempts from public,anon,authenticated,service_role;
grant select,insert on public.public_evidence_captures,public.public_evidence_observations,
    public.public_evidence_decisions,public.public_evidence_collection_attempts to service_role;
commit;
