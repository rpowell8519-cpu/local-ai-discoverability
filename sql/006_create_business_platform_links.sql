-- Multi-platform review ingestion (Sprint 1): a business has no stored Yelp or
-- TripAdvisor identifier anywhere (business_features/raw_outscraper_locations
-- only carry what Google's own Outscraper import gives us). Yelp/TripAdvisor
-- reviews are pulled by page URL, not by Google Place ID, so that URL has to
-- be captured somewhere before a pull can run.
--
-- Per rob (2026-09-27): no attempt at automatic identity-matching across
-- platforms — a person finds the business on the platform themselves and
-- pastes the URL in, same manual-confirmation spirit as
-- competitor_relationship_reviews.

begin;

create table if not exists public.business_platform_links (
    google_place_id text not null,
    platform text not null,
    external_url text not null,
    added_by text,
    added_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (google_place_id, platform),
    constraint business_platform_links_platform_check
        check (platform in ('yelp', 'tripadvisor', 'checkatrade')),
    constraint business_platform_links_url_check
        check (external_url ~* '^https?://[^[:space:]]+$')
);

commit;
