-- Additional owner context and a manually supplied website URL for the
-- end-to-end generic report workflow.

begin;

alter table public.report_audit_revisions
    add column owner_context jsonb not null default '{}'::jsonb,
    add column manual_website_url text;

alter table public.report_audit_revisions
    add constraint report_audit_revisions_owner_context_check
        check (jsonb_typeof(owner_context) = 'object'),
    add constraint report_audit_revisions_manual_website_check
        check (
            manual_website_url is null
            or manual_website_url ~* '^https?://[^[:space:]]+$'
        );

commit;
