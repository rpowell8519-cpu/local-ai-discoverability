-- Client account action plans (beta): DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires 20261016120000_client_accounts.sql.
-- Adds one store: an action plan for one of a client's services, published by an operator from the Streamlit
-- "Client accounts" page and read by the client's members on the website. Like published tests, a plan is a
-- frozen copy: changing an action's status publishes a new version and withdraws the previous one in the same
-- transaction, so the history of every status is kept. No backfill; no existing rows or policies change. The
-- one existing object changed is the publication guard, made table-agnostic with the same behaviour.
begin;

create table public.client_account_plans (
    id uuid primary key default gen_random_uuid(),
    client_id uuid not null references public.client_accounts(id) on delete cascade,
    service text not null check (char_length(btrim(service)) between 1 and 60),
    title text not null check (char_length(btrim(title)) between 1 and 160),
    summary text check (summary is null or char_length(summary) <= 1200),
    -- [{number, title, timing, owner, status, why, what, complete_when, progress}], status one of
    -- proposed | agreed | in_progress | done | not_doing. Validated by the platform before publishing.
    actions jsonb not null check (jsonb_typeof(actions) = 'array' and jsonb_array_length(actions) between 1 and 40),
    report_id uuid references public.client_account_reports(id) on delete set null,
    published_by text not null check (char_length(btrim(published_by)) between 1 and 80),
    published_at timestamptz not null default now(),
    withdrawn_at timestamptz
);
create unique index client_account_plans_current_idx on public.client_account_plans(client_id, service, title)
    where withdrawn_at is null;

-- Same rule for every published store: only withdrawn_at may change, once.
create or replace function public.guard_client_account_publication() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if (to_jsonb(NEW) - 'withdrawn_at') is distinct from (to_jsonb(OLD) - 'withdrawn_at') then
        raise exception 'A published % row cannot be changed; withdraw it and publish again', TG_TABLE_NAME;
    end if;
    if OLD.withdrawn_at is not null and NEW.withdrawn_at is distinct from OLD.withdrawn_at then
        raise exception 'A withdrawal cannot be undone; publish again';
    end if;
    return NEW;
end;
$$;
create trigger guard_client_account_plans before update on public.client_account_plans
    for each row execute function public.guard_client_account_publication();

alter table public.client_account_plans enable row level security;
revoke all on public.client_account_plans from public, anon, authenticated, service_role;
grant select (id, client_id, service, title, summary, actions, report_id, published_at, withdrawn_at)
    on public.client_account_plans to authenticated;
grant select, insert, update on public.client_account_plans to service_role;
create policy client_account_plans_member_select on public.client_account_plans
    for select to authenticated using (withdrawn_at is null and client_id in (select public.current_client_account_ids()));
commit;
