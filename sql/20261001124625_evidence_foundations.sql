-- Increment A: additive operator-only stores. DRAFT: explicit approval required before application.
-- Generated with Supabase CLI 2.119.0; retained in this project's existing sql/ convention.
-- No historical runs, snapshots, raw listings or review records are updated/backfilled.
begin;

create table public.proposition_catalog (
    proposition_key text primary key check (length(btrim(proposition_key)) > 0),
    label text not null check (length(btrim(label)) > 0),
    catalogue_version text not null,
    created_at timestamptz not null default now()
);
create table public.proposition_aliases (
    alias_key text primary key check (length(btrim(alias_key)) > 0),
    alias_text text not null,
    proposition_key text not null references public.proposition_catalog(proposition_key),
    catalogue_version text not null,
    created_at timestamptz not null default now()
);
create index proposition_aliases_proposition_idx on public.proposition_aliases(proposition_key);

create table public.review_profile_metrics (
    id uuid primary key default gen_random_uuid(),
    google_place_id text not null references public.business_features(google_place_id),
    platform text not null check (length(btrim(platform)) > 0),
    rating numeric check (rating between 1 and 5),
    published_review_count bigint check (published_review_count >= 0),
    observed_at timestamptz not null check (observed_at <= now()),
    source_record_id text not null,
    source_url text check (source_url ~* '^https?://[^[:space:]]+$'),
    adapter_version text not null,
    evidence_sha256 text not null check (evidence_sha256 ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null default now(),
    unique (google_place_id, platform, source_record_id, adapter_version)
);
create index review_profile_metrics_business_time_idx
    on public.review_profile_metrics(google_place_id, platform, observed_at desc, id desc);

create table public.ai_measurement_waves (
    run_id uuid primary key references public.ai_visibility_runs(id),
    series_id uuid not null,
    panel_id text not null,
    panel_kind text not null check (panel_kind in ('core', 'focused')),
    configuration_sha256 text not null check (configuration_sha256 ~ '^[a-f0-9]{64}$'),
    configuration jsonb not null check (jsonb_typeof(configuration) = 'object'),
    created_at timestamptz not null default now(),
    check (panel_id = configuration_sha256),
    check (configuration ?& array['version', 'panel_kind']),
    check (configuration->>'panel_kind' = panel_kind),
    check (configuration->>'version' = 'measurement-panel-v1')
);
create index ai_measurement_waves_config_idx on public.ai_measurement_waves(configuration_sha256, created_at desc);
create index ai_measurement_waves_series_idx on public.ai_measurement_waves(series_id, created_at);

create function public.reject_evidence_foundation_change() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    raise exception 'Evidence observations and measurement waves are append-only';
end;
$$;
revoke all on function public.reject_evidence_foundation_change() from public, anon, authenticated;
grant execute on function public.reject_evidence_foundation_change() to service_role;
create trigger immutable_review_profile_metrics before update or delete on public.review_profile_metrics
    for each row execute function public.reject_evidence_foundation_change();
create trigger immutable_ai_measurement_waves before update or delete on public.ai_measurement_waves
    for each row execute function public.reject_evidence_foundation_change();

alter table public.proposition_catalog enable row level security;
alter table public.proposition_aliases enable row level security;
alter table public.review_profile_metrics enable row level security;
alter table public.ai_measurement_waves enable row level security;
revoke all on public.proposition_catalog, public.proposition_aliases,
    public.review_profile_metrics, public.ai_measurement_waves from public, anon, authenticated;
grant select, insert on public.proposition_catalog, public.proposition_aliases,
    public.review_profile_metrics, public.ai_measurement_waves to service_role;

-- Starter vocabulary is appended below. It asserts no business positioning or tested intent.
insert into public.proposition_catalog (proposition_key, label, catalogue_version) values
    ('balayage', 'Balayage', 'propositions-v1'),
    ('curly_hair', 'Curly hair', 'propositions-v1'),
    ('bridal_hair', 'Bridal hair', 'propositions-v1'),
    ('colour_correction', 'Colour correction', 'propositions-v1'),
    ('hair_extensions', 'Hair extensions', 'propositions-v1'),
    ('childrens_haircuts', 'Children''s haircuts', 'propositions-v1'),
    ('quiet_appointments', 'Quiet appointments', 'propositions-v1'),
    ('private_dining', 'Private dining', 'propositions-v1'),
    ('wine_selection', 'Wine selection', 'propositions-v1'),
    ('family_friendly', 'Family friendly', 'propositions-v1'),
    ('coworking', 'Co-working', 'propositions-v1'),
    ('private_offices', 'Private offices', 'propositions-v1'),
    ('meeting_rooms', 'Meeting rooms', 'propositions-v1'),
    ('commercial_cleaning', 'Commercial cleaning', 'propositions-v1'),
    ('office_cleaning', 'Office cleaning', 'propositions-v1'),
    ('end_of_tenancy_cleaning', 'End of tenancy cleaning', 'propositions-v1'),
    ('carpet_cleaning', 'Carpet cleaning', 'propositions-v1'),
    ('upholstery_cleaning', 'Upholstery cleaning', 'propositions-v1');

insert into public.proposition_aliases (alias_key, alias_text, proposition_key, catalogue_version) values
    ('balayage', 'Balayage', 'balayage', 'propositions-v1'),
    ('curly hair', 'Curly hair', 'curly_hair', 'propositions-v1'),
    ('curly-hair expertise', 'Curly-hair expertise', 'curly_hair', 'propositions-v1'),
    ('bridal hair', 'Bridal hair', 'bridal_hair', 'propositions-v1'),
    ('wedding hair', 'Wedding hair', 'bridal_hair', 'propositions-v1'),
    ('bridal / wedding hair', 'Bridal / wedding hair', 'bridal_hair', 'propositions-v1'),
    ('colour correction', 'Colour correction', 'colour_correction', 'propositions-v1'),
    ('color correction', 'Color correction', 'colour_correction', 'propositions-v1'),
    ('hair extensions', 'Hair extensions', 'hair_extensions', 'propositions-v1'),
    ('children''s haircuts', 'Children''s haircuts', 'childrens_haircuts', 'propositions-v1'),
    ('quiet appointments', 'Quiet appointments', 'quiet_appointments', 'propositions-v1'),
    ('private dining', 'Private dining', 'private_dining', 'propositions-v1'),
    ('wine selection', 'Wine selection', 'wine_selection', 'propositions-v1'),
    ('wine list', 'Wine list', 'wine_selection', 'propositions-v1'),
    ('a great wine list', 'A great wine list', 'wine_selection', 'propositions-v1'),
    ('family friendly', 'Family friendly', 'family_friendly', 'propositions-v1'),
    ('family-friendly', 'Family-friendly', 'family_friendly', 'propositions-v1'),
    ('co-working', 'Co-working', 'coworking', 'propositions-v1'),
    ('coworking', 'Coworking', 'coworking', 'propositions-v1'),
    ('co working', 'Co working', 'coworking', 'propositions-v1'),
    ('private offices', 'Private offices', 'private_offices', 'propositions-v1'),
    ('meeting rooms', 'Meeting rooms', 'meeting_rooms', 'propositions-v1'),
    ('commercial cleaning', 'Commercial cleaning', 'commercial_cleaning', 'propositions-v1'),
    ('office cleaning', 'Office cleaning', 'office_cleaning', 'propositions-v1'),
    ('end of tenancy cleaning', 'End of tenancy cleaning', 'end_of_tenancy_cleaning', 'propositions-v1'),
    ('carpet cleaning', 'Carpet cleaning', 'carpet_cleaning', 'propositions-v1'),
    ('upholstery cleaning', 'Upholstery cleaning', 'upholstery_cleaning', 'propositions-v1');

commit;
