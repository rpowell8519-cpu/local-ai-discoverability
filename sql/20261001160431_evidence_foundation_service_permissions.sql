-- Increment A verification correction: Supabase default grants include ALL for service_role.
-- Restrict the same four approved stores to the intended SELECT/INSERT permissions.
-- No rows, table definitions, client access or project-wide default privileges are changed.
begin;
revoke all on public.proposition_catalog, public.proposition_aliases,
    public.review_profile_metrics, public.ai_measurement_waves from service_role;
grant select, insert on public.proposition_catalog, public.proposition_aliases,
    public.review_profile_metrics, public.ai_measurement_waves to service_role;
commit;
