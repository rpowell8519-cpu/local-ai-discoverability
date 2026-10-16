-- Client account area (beta): DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires 20261003120100_customer_free_checks.sql (same access model).
-- Adds four stores for the signed-in client account area on the website. The website never reads
-- live test tables: an operator publishes a frozen, client-safe copy of each reviewed test from the
-- Streamlit "Client accounts" page, and the website reads only those copies. No backfill; no existing
-- table, row or policy changes.
-- Access model: a signed-in person may SELECT the rows of the client accounts their email address is
-- a current member of, and nothing else. Every write goes through the Python platform (operator).
-- Withdrawn tests and reports, and removed members, are hidden from clients but kept.
begin;

create table public.client_accounts (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,40}$'),
    name text not null check (char_length(btrim(name)) between 1 and 120),
    -- Each service has its own Google Place ID, e.g. WRAP Coworking and WRAP Nursery.
    services jsonb not null default '[]'::jsonb check (jsonb_typeof(services) = 'array'),
    next_test_note text check (next_test_note is null or char_length(next_test_note) <= 200),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.client_account_members (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references public.client_accounts(id) on delete cascade,
    email text not null check (email = lower(btrim(email)) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    display_name text check (display_name is null or char_length(btrim(display_name)) between 1 and 80),
    added_by text not null check (char_length(btrim(added_by)) between 1 and 80),
    added_at timestamptz not null default now(),
    removed_at timestamptz
);
create unique index client_account_members_current_idx on public.client_account_members(client_id, email)
    where removed_at is null;
create index client_account_members_email_idx on public.client_account_members(email) where removed_at is null;

-- One published test: the reviewed counts for one service on one test day, frozen. It may combine
-- several runs from the same day (WRAP Coworking on 9 October was split across two runs).
create table public.client_account_tests (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references public.client_accounts(id) on delete cascade,
    service text not null check (char_length(btrim(service)) between 1 and 60),
    google_place_id text not null,
    tested_on date not null,
    run_ids uuid[] not null check (cardinality(run_ids) between 1 and 6 and array_position(run_ids, null) is null),
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    payload_version text not null,
    -- The operator's name decisions for this test, carried forward to the next one. Never shown to clients.
    decisions jsonb not null check (jsonb_typeof(decisions) = 'object'),
    note text check (note is null or char_length(note) <= 1200),
    published_by text not null check (char_length(btrim(published_by)) between 1 and 80),
    published_at timestamptz not null default now(),
    withdrawn_at timestamptz
);
create unique index client_account_tests_current_idx on public.client_account_tests(client_id, service, tested_on)
    where withdrawn_at is null;

create table public.client_account_reports (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references public.client_accounts(id) on delete cascade,
    service text not null check (char_length(btrim(service)) between 1 and 60),
    title text not null check (char_length(btrim(title)) between 1 and 160),
    report_date date not null,
    file_name text not null check (file_name ~ '^[A-Za-z0-9._ -]{1,120}\.pdf$'),
    pdf_bytes bytea not null check (octet_length(pdf_bytes) between 1 and 20000000),
    published_by text not null check (char_length(btrim(published_by)) between 1 and 80),
    published_at timestamptz not null default now(),
    withdrawn_at timestamptz
);
create index client_account_reports_client_idx on public.client_account_reports(client_id) where withdrawn_at is null;

-- Only the two columns that may change after publishing: withdrawing, and nothing else.
create function public.guard_client_account_publication() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if TG_TABLE_NAME = 'client_account_tests' and (to_jsonb(NEW) - 'withdrawn_at') is distinct from (to_jsonb(OLD) - 'withdrawn_at') then
        raise exception 'A published test cannot be changed; withdraw it and publish again';
    end if;
    if TG_TABLE_NAME = 'client_account_reports' and (to_jsonb(NEW) - 'withdrawn_at') is distinct from (to_jsonb(OLD) - 'withdrawn_at') then
        raise exception 'A published report cannot be changed; withdraw it and publish again';
    end if;
    if OLD.withdrawn_at is not null and NEW.withdrawn_at is distinct from OLD.withdrawn_at then
        raise exception 'A withdrawal cannot be undone; publish again';
    end if;
    return NEW;
end;
$$;
create trigger guard_client_account_tests before update on public.client_account_tests
    for each row execute function public.guard_client_account_publication();
create trigger guard_client_account_reports before update on public.client_account_reports
    for each row execute function public.guard_client_account_publication();

-- The client accounts the signed-in email address currently belongs to. SECURITY DEFINER so the
-- policies below can consult memberships without the members policy referring to itself.
create function public.current_client_account_ids() returns setof uuid
language sql stable security definer set search_path = '' as $$
    select m.client_id from public.client_account_members m
    where m.removed_at is null and m.email = lower((select auth.jwt()) ->> 'email');
$$;

revoke all on function public.guard_client_account_publication() from public, anon, authenticated;
revoke all on function public.current_client_account_ids() from public, anon;
grant execute on function public.current_client_account_ids() to authenticated;

alter table public.client_accounts enable row level security;
alter table public.client_account_members enable row level security;
alter table public.client_account_tests enable row level security;
alter table public.client_account_reports enable row level security;
revoke all on public.client_accounts, public.client_account_members, public.client_account_tests,
    public.client_account_reports from public, anon, authenticated, service_role;
-- Clients read only what the website shows: never the operator's decisions, run IDs or who published.
grant select on public.client_accounts, public.client_account_reports to authenticated;
grant select (id, client_id, email, display_name, added_at, removed_at) on public.client_account_members to authenticated;
grant select (id, client_id, service, tested_on, payload, payload_version, note, published_at, withdrawn_at)
    on public.client_account_tests to authenticated;
grant select, insert, update on public.client_accounts, public.client_account_members, public.client_account_tests,
    public.client_account_reports to service_role;

create policy client_accounts_member_select on public.client_accounts
    for select to authenticated using (id in (select public.current_client_account_ids()));
create policy client_account_members_member_select on public.client_account_members
    for select to authenticated using (removed_at is null and client_id in (select public.current_client_account_ids()));
create policy client_account_tests_member_select on public.client_account_tests
    for select to authenticated using (withdrawn_at is null and client_id in (select public.current_client_account_ids()));
create policy client_account_reports_member_select on public.client_account_reports
    for select to authenticated using (withdrawn_at is null and client_id in (select public.current_client_account_ids()));
commit;
