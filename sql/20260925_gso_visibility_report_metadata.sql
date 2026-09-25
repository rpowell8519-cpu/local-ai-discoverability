-- Optional: apply only with explicit database-schema approval to persist metadata
-- for future scans. Report downloads support the existing schema without this SQL.
-- Existing result text and identity analysis remain untouched. Historical citation
-- coverage is unknown, so the JSON default deliberately records it as unavailable.

ALTER TABLE public.ai_visibility_queries
    ADD COLUMN IF NOT EXISTS report_intent text NOT NULL DEFAULT 'discovery',
    ADD COLUMN IF NOT EXISTS report_importance smallint,
    ADD COLUMN IF NOT EXISTS report_effort smallint;

ALTER TABLE public.ai_visibility_results
    ADD COLUMN IF NOT EXISTS report_metadata jsonb NOT NULL DEFAULT
        '{"capture_version":"legacy-unavailable","citation_status":"unavailable","citations":[],"refused":false}'::jsonb;
