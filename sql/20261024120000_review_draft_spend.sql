-- Review assistant daily spending cap: DRAFT ONLY. Explicit approval required before applying to Supabase.
-- The website's review assistant (foundinbrighton.ai/review/...) asks OpenAI to draft customers' reviews. Before
-- each draft it reserves that draft's worst-case cost against one shared allowance per UK day, so every server
-- instance counts against the same cap. The cap itself lives in the site's code (lib/review/cost.ts), and only
-- the server, with the service role key, can call this. Stores counts and amounts only: no review text, ratings
-- or customer details. New objects only; nothing existing changes.
begin;

create table public.review_draft_spend (
    day date primary key, -- Europe/London
    drafts integer not null default 0 check (drafts >= 0),
    reserved_microdollars bigint not null default 0 check (reserved_microdollars >= 0)
);
alter table public.review_draft_spend enable row level security;
revoke all on public.review_draft_spend from public, anon, authenticated, service_role;
grant select on public.review_draft_spend to service_role;

-- Adds one draft to today's row if its cost still fits under the cap; returns whether it did. The conditional
-- update takes the row lock, so concurrent drafts cannot together pass the cap.
create function public.reserve_review_draft(p_microdollars bigint, p_cap_microdollars bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
    v_day date := (now() at time zone 'Europe/London')::date;
    v_reserved boolean;
begin
    if p_microdollars is null or p_microdollars <= 0 or p_cap_microdollars is null or p_cap_microdollars <= 0 then
        raise exception 'Draft cost and cap must be positive';
    end if;
    insert into public.review_draft_spend (day) values (v_day) on conflict (day) do nothing;
    update public.review_draft_spend
       set drafts = drafts + 1, reserved_microdollars = reserved_microdollars + p_microdollars
     where day = v_day and reserved_microdollars + p_microdollars <= p_cap_microdollars
    returning true into v_reserved;
    return coalesce(v_reserved, false);
end;
$$;
revoke all on function public.reserve_review_draft(bigint, bigint) from public, anon, authenticated;
grant execute on function public.reserve_review_draft(bigint, bigint) to service_role;
commit;
