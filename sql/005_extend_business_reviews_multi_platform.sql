-- Multi-platform review ingestion (Sprint 1): Yelp and TripAdvisor, via Outscraper.
--
-- review_rating stays the single canonical value every existing reader already
-- assumes (Google, Yelp and TripAdvisor are all native 1-5 star scales, so no
-- normalisation is needed for this sprint). The columns below only carry
-- platform-specific extras that don't fit that column, and stay unused/NULL
-- until a future non-5-star source (e.g. Checkatrade, out of 10) needs them.
--
-- business_reviews itself has no CREATE TABLE in this repo (bootstrapped
-- directly in Supabase, like report_audit_revisions originally was), so this
-- uses "add column if not exists" defensively rather than assuming the exact
-- current definition.

begin;

-- platform_review_url was dropped from this draft: review_link/location_link
-- already carry that generically for every source, including Google today.
alter table public.business_reviews
    add column if not exists platform_rating_scale text,
    add column if not exists platform_rating_raw numeric(4, 1),
    add column if not exists sub_ratings jsonb;

alter table public.business_reviews
    add constraint business_reviews_sub_ratings_check
        check (sub_ratings is null or jsonb_typeof(sub_ratings) = 'object');

commit;
