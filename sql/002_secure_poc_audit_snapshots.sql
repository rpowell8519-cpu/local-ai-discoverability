-- Keep immutable client report snapshots private to trusted server-side roles.
-- The Streamlit application connects through its server-side PostgreSQL role.

begin;

revoke all privileges
on table public.poc_audit_snapshots
from anon, authenticated;

alter table public.poc_audit_snapshots
    enable row level security;

commit;
