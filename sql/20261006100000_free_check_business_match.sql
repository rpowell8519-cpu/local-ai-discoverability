-- Free check: "Is this you?" DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires 20261003120100_customer_free_checks.sql.
-- Lets an owner confirm which listing in the business directory is theirs before a free check runs,
-- so the check measures the verified listing (and its known name variants) instead of typed text.
-- Adds one nullable column, two server-only read functions, and replaces the submit function with
-- one that accepts the confirmed listing. No rows change; existing calls keep working because the
-- new argument is optional. Customers still cannot write to any table or call any function.
begin;

alter table public.customer_checks
    add column claimed_google_place_id text references public.business_features(google_place_id);
create index customer_checks_claimed_place_idx on public.customer_checks(claimed_google_place_id);

-- Compare names the way a person would: case, punctuation, "&" versus "and" and a leading "The"
-- do not make two names different.
create function public.normalise_business_name(p_name text) returns text
language sql immutable security invoker set search_path = '' as $$
    select regexp_replace(
        btrim(regexp_replace(
            regexp_replace(replace(replace(lower(coalesce(p_name, '')), '&', ' and '), '’', ''), '''', '', 'g'),
            '[^a-z0-9]+', ' ', 'g')),
        '^the ', '');
$$;

-- Up to five directory listings whose name matches what the owner typed. An exact match (after
-- normalising) always qualifies; a partial match needs at least six characters, so a generic word
-- cannot pull in unrelated businesses. Returns public listing details only.
create function public.match_business_directory(p_name text, p_limit integer default 3)
returns table (google_place_id text, business_name text, street text, city text, category text)
language sql stable security invoker set search_path = '' as $$
    with typed as (select public.normalise_business_name(p_name) as name),
    listed as (
        select b.google_place_id, b.business_name, b.raw_category,
               public.normalise_business_name(b.business_name) as name
        from public.business_features b
    )
    select l.google_place_id, l.business_name, place.street, place.city, l.raw_category
    from listed l
    cross join typed t
    left join lateral (
        select nullif(btrim(r.raw_data->>'street'), '') as street,
               nullif(btrim(r.raw_data->>'city'), '') as city
        from public.raw_outscraper_locations r
        where r.google_place_id = l.google_place_id
        order by r.created_at desc
        limit 1
    ) place on true
    where char_length(t.name) >= 3
      and (l.name = t.name
           or (char_length(t.name) >= 6 and l.name like '%' || t.name || '%')
           or (char_length(l.name) >= 6 and t.name like '%' || l.name || '%'))
    order by (l.name = t.name) desc, abs(char_length(l.name) - char_length(t.name)), l.business_name
    limit least(greatest(coalesce(p_limit, 3), 1), 5);
$$;

-- The confirmed listing is part of the frozen brief.
create or replace function public.guard_customer_check_update() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if (NEW.id, NEW.owner_user_id, NEW.idempotency_key, NEW.entitlement, NEW.brief_version, NEW.business_name,
        NEW.location, NEW.services, NEW.competitors, NEW.questions, NEW.created_at)
       is distinct from
       (OLD.id, OLD.owner_user_id, OLD.idempotency_key, OLD.entitlement, OLD.brief_version, OLD.business_name,
        OLD.location, OLD.services, OLD.competitors, OLD.questions, OLD.created_at)
       or NEW.website is distinct from OLD.website
       or NEW.claimed_google_place_id is distinct from OLD.claimed_google_place_id then
        raise exception 'A submitted check brief and its owner cannot be changed';
    end if;
    NEW.updated_at := now();
    return NEW;
end;
$$;

drop function public.submit_customer_check(uuid, text, text, text, text, text, text[], text[], integer);
create function public.submit_customer_check(
    p_owner_user_id uuid, p_idempotency_key text, p_business_name text, p_website text, p_location text,
    p_services text, p_competitors text[], p_questions text[], p_reserved_calls integer,
    p_claimed_google_place_id text default null
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
        (owner_user_id, idempotency_key, business_name, website, location, services, competitors, questions,
         claimed_google_place_id)
    values (p_owner_user_id, p_idempotency_key, p_business_name, nullif(btrim(p_website), ''), p_location,
            p_services, coalesce(p_competitors, '{}'), p_questions, nullif(btrim(p_claimed_google_place_id), ''))
    returning * into submitted;
    insert into public.visibility_jobs (check_id, reserved_calls) values (submitted.id, p_reserved_calls);
    return submitted;
end;
$$;

revoke all on function public.normalise_business_name(text) from public, anon, authenticated;
revoke all on function public.match_business_directory(text, integer) from public, anon, authenticated;
revoke all on function
    public.submit_customer_check(uuid, text, text, text, text, text, text[], text[], integer, text)
    from public, anon, authenticated;
grant execute on function public.normalise_business_name(text) to service_role;
grant execute on function public.match_business_directory(text, integer) to service_role;
grant execute on function
    public.submit_customer_check(uuid, text, text, text, text, text, text[], text[], integer, text)
    to service_role;
commit;
