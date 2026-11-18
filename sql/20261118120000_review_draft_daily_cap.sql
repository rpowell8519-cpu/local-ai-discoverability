-- Review assistant: a shared daily cap on AI drafts. DRAFT ONLY. Explicit approval from Rob required before
-- applying to Supabase.
--
-- The website's review assistant (foundinbrighton.ai/review/...) asks OpenAI to draft customers' reviews. Before
-- each draft the live site calls reserve_review_draft(cap); it counts the draft against one total per UK day, so
-- every server instance shares the same cap. The cap itself (1,000 a day) lives in the website's code
-- (lib/review/spend.ts). Over the cap, drafting stops and customers write their own review; the rest of the page
-- is unaffected. The website already treats this function's absence, or any database error, as "go ahead", so
-- the website change can be live before this is applied, and applying it only adds the cap.
--
-- Replaces the unapplied draft 20261024120000_review_draft_spend.sql (a cost-based cap that could block real
-- customers after a dozen drafts if the model setting changed to one missing from its price table).
-- Stores a date and a count only: no review text, ratings or customer details. New objects only.
begin;

create table public.review_draft_daily (
    day date primary key, -- Europe/London
    drafts integer not null default 0 check (drafts >= 0)
);
alter table public.review_draft_daily enable row level security;
revoke all on public.review_draft_daily from public, anon, authenticated, service_role;
grant select on public.review_draft_daily to service_role;

-- Adds one draft to today's count if it is still under the cap; returns whether it did. The conditional update
-- takes the row lock, so concurrent drafts cannot together pass the cap.
create function public.reserve_review_draft(p_cap integer) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
    v_day date := (now() at time zone 'Europe/London')::date;
    v_reserved boolean;
begin
    if p_cap is null or p_cap <= 0 then
        raise exception 'Cap must be positive';
    end if;
    insert into public.review_draft_daily (day) values (v_day) on conflict (day) do nothing;
    update public.review_draft_daily
       set drafts = drafts + 1
     where day = v_day and drafts < p_cap
    returning true into v_reserved;
    return coalesce(v_reserved, false);
end;
$$;
revoke all on function public.reserve_review_draft(integer) from public, anon, authenticated;
grant execute on function public.reserve_review_draft(integer) to service_role;

commit;
