-- Free check: three questions instead of five. DRAFT ONLY. Explicit approval required before applying to Supabase.
-- Requires 20261003120100_customer_free_checks.sql.
-- Replaces one check constraint on customer_checks.questions so a new check may carry three
-- questions. Five stays valid because checks already submitted with five questions are frozen and
-- must keep passing. The combined-length floor drops from 50 to 30 characters, matching three
-- questions of at least 10 characters each. No rows, functions, grants or policies change.
-- Apply before the website starts sending three questions: until then a three-question submission
-- is rejected by the old constraint. Five-question submissions keep working throughout.
begin;

alter table public.customer_checks drop constraint customer_checks_questions_check;
alter table public.customer_checks add constraint customer_checks_questions_check
    check (cardinality(questions) in (3, 5) and array_position(questions, null) is null
           and char_length(array_to_string(questions, '')) between 30 and 1500);

commit;
