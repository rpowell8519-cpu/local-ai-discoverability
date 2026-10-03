-- Free check groundwork 2 of 2: DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires 20261001124625_evidence_foundations.sql and 20261003120000_revoke_legacy_client_grants.sql.
-- Adds the first customer-owned stores: one free visibility check per verified account, plus the
-- worker-only job that executes it. No backfill; no existing rows, policies or report tables change.
-- The only change to an existing object is allowing panel_kind 'free_check' on ai_measurement_waves,
-- so a free-check run is durably marked on the run itself. core_run_filter in
-- src/ai_visibility_repository.py must exclude that kind before any free check is executed.
-- Access model: signed-in customers may only SELECT their own customer_checks rows. Every write
-- goes through the server (service_role) or the Python worker; customers never write directly.
begin;

alter table public.ai_measurement_waves drop constraint ai_measurement_waves_panel_kind_check;
alter table public.ai_measurement_waves add constraint ai_measurement_waves_panel_kind_check
    check (panel_kind in ('core', 'focused', 'free_check'));

create table public.customer_checks (
    id uuid primary key default gen_random_uuid(),
    owner_user_id uuid not null references auth.users(id) on delete cascade,
    idempotency_key text not null check (idempotency_key ~ '^[A-Za-z0-9_-]{16,128}$'),
    entitlement text not null default 'free' check (entitlement = 'free'),
    brief_version text not null default 'free-check-brief-v1' check (brief_version = 'free-check-brief-v1'),
    business_name text not null check (char_length(btrim(business_name)) between 1 and 120),
    website text check (website is null or char_length(btrim(website)) between 4 and 250),
    location text not null check (char_length(btrim(location)) between 1 and 120),
    services text not null check (char_length(btrim(services)) between 1 and 500),
    competitors text[] not null default '{}'
        check (cardinality(competitors) <= 3 and array_position(competitors, null) is null),
    questions text[] not null
        check (cardinality(questions) = 5 and array_position(questions, null) is null
               and char_length(array_to_string(questions, '')) between 50 and 1500),
    status text not null default 'queued'
        check (status in ('queued', 'running', 'completed', 'partial', 'failed')),
    run_id uuid references public.ai_visibility_runs(id) on delete set null,
    result_projection jsonb check (result_projection is null or jsonb_typeof(result_projection) = 'object'),
    result_projection_version text,
    error_code text check (error_code is null or error_code ~ '^[a-z0-9_]{1,64}$'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (owner_user_id, idempotency_key),
    check ((result_projection is null) = (result_projection_version is null)),
    check (result_projection is null or status in ('completed', 'partial')),
    check (error_code is null or status in ('partial', 'failed'))
);
-- One free check per account. A check that failed outright does not use up the entitlement.
create unique index customer_checks_one_free_per_owner_idx on public.customer_checks(owner_user_id)
    where entitlement = 'free' and status <> 'failed';
create index customer_checks_run_idx on public.customer_checks(run_id);

create table public.visibility_jobs (
    id uuid primary key default gen_random_uuid(),
    check_id uuid not null unique references public.customer_checks(id) on delete cascade,
    state text not null default 'queued'
        check (state in ('queued', 'leased', 'succeeded', 'failed', 'cancelled')),
    run_id uuid references public.ai_visibility_runs(id) on delete set null,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 3 check (max_attempts between 1 and 10),
    lease_owner text,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    next_attempt_at timestamptz not null default now(),
    reserved_calls integer not null check (reserved_calls between 1 and 60),
    completed_calls integer not null default 0 check (completed_calls >= 0),
    last_error text check (last_error is null or char_length(last_error) <= 500),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    check ((state = 'leased') = (lease_owner is not null)),
    check ((lease_owner is null) = (lease_expires_at is null)),
    check (attempt_count <= max_attempts),
    check ((completed_at is not null) = (state in ('succeeded', 'failed', 'cancelled')))
);
create index visibility_jobs_claim_idx on public.visibility_jobs(next_attempt_at) where state = 'queued';
create index visibility_jobs_lease_idx on public.visibility_jobs(lease_expires_at) where state = 'leased';
create index visibility_jobs_run_idx on public.visibility_jobs(run_id);

create function public.guard_customer_check_update() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if (NEW.id, NEW.owner_user_id, NEW.idempotency_key, NEW.entitlement, NEW.brief_version, NEW.business_name,
        NEW.location, NEW.services, NEW.competitors, NEW.questions, NEW.created_at)
       is distinct from
       (OLD.id, OLD.owner_user_id, OLD.idempotency_key, OLD.entitlement, OLD.brief_version, OLD.business_name,
        OLD.location, OLD.services, OLD.competitors, OLD.questions, OLD.created_at)
       or NEW.website is distinct from OLD.website then
        raise exception 'A submitted check brief and its owner cannot be changed';
    end if;
    NEW.updated_at := now();
    return NEW;
end;
$$;
create trigger guard_customer_checks before update on public.customer_checks
    for each row execute function public.guard_customer_check_update();

create function public.touch_visibility_job() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if NEW.check_id is distinct from OLD.check_id then
        raise exception 'A job cannot move to another check';
    end if;
    NEW.updated_at := now();
    return NEW;
end;
$$;
create trigger touch_visibility_jobs before update on public.visibility_jobs
    for each row execute function public.touch_visibility_job();

-- Atomic, idempotent submission. Repeating the same key returns the original check and reserves
-- nothing further; a different key from an account that has used its free check raises unique_violation.
create function public.submit_customer_check(
    p_owner_user_id uuid, p_idempotency_key text, p_business_name text, p_website text, p_location text,
    p_services text, p_competitors text[], p_questions text[], p_reserved_calls integer
) returns public.customer_checks
language plpgsql security invoker set search_path = '' as $$
declare
    submitted public.customer_checks;
begin
    perform pg_advisory_xact_lock(hashtextextended('customer-check:' || p_owner_user_id::text, 0));
    select * into submitted from public.customer_checks
        where owner_user_id = p_owner_user_id and idempotency_key = p_idempotency_key;
    if submitted.id is not null then
        return submitted;
    end if;
    insert into public.customer_checks
        (owner_user_id, idempotency_key, business_name, website, location, services, competitors, questions)
    values (p_owner_user_id, p_idempotency_key, p_business_name, nullif(btrim(p_website), ''), p_location,
            p_services, coalesce(p_competitors, '{}'), p_questions)
    returning * into submitted;
    insert into public.visibility_jobs (check_id, reserved_calls) values (submitted.id, p_reserved_calls);
    return submitted;
end;
$$;

revoke all on function public.guard_customer_check_update() from public, anon, authenticated;
revoke all on function public.touch_visibility_job() from public, anon, authenticated;
revoke all on function public.submit_customer_check(uuid, text, text, text, text, text, text[], text[], integer)
    from public, anon, authenticated;
grant execute on function public.guard_customer_check_update() to service_role;
grant execute on function public.touch_visibility_job() to service_role;
grant execute on function public.submit_customer_check(uuid, text, text, text, text, text, text[], text[], integer)
    to service_role;

alter table public.customer_checks enable row level security;
alter table public.visibility_jobs enable row level security;
revoke all on public.customer_checks, public.visibility_jobs from public, anon, authenticated, service_role;
grant select on public.customer_checks to authenticated;
grant select, insert, update on public.customer_checks, public.visibility_jobs to service_role;
create policy customer_checks_owner_select on public.customer_checks
    for select to authenticated using (owner_user_id = (select auth.uid()));
commit;
