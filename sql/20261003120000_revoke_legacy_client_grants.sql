-- Free check groundwork 1 of 2: DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Removes the Supabase default grants that 22 older tables still carry for the public API roles
-- (anon, authenticated). Row level security with no policies already denies those roles every row;
-- this removes the latent privilege so a future policy mistake cannot expose an internal table.
-- Also stops tables and sequences later created by postgres in public from inheriting those grants.
-- No rows, table definitions, policies, service_role grants or postgres access are changed.
-- Not changed: supabase_admin's own default privileges (postgres cannot alter them) and the
-- default EXECUTE that PostgreSQL gives PUBLIC on new functions.
begin;
revoke all on table
    public.ai_competitor_enrichment_queue,
    public.ai_visibility_queries,
    public.ai_visibility_results,
    public.ai_visibility_runs,
    public.business_aliases,
    public.business_classifications,
    public.business_entity_aliases,
    public.business_features,
    public.business_platform_links,
    public.business_reviews,
    public.businesses,
    public.cohort_memberships,
    public.competitor_relationship_reviews,
    public.data_imports,
    public.google_profiles,
    public.locations,
    public.raw_outscraper_locations,
    public.review_analysis_runs,
    public.review_import_batches,
    public.review_themes,
    public.website_audit_pages,
    public.website_audit_runs
from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
commit;
