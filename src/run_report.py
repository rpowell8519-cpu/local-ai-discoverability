"""Command line for the report runner: brief, plan, paid run and status, without the Streamlit screens.

    python -m src.run_report find "Business name"           # read-only: find the Google listing
    python -m src.run_report brief path/to/brief.toml       # read-only: check the brief, show what would change
    python -m src.run_report brief path/to/brief.toml --save [--replace-current]
    python -m src.run_report plan <place-id> [--repeats 3]  # read-only: the paid test and its approval code
    python -m src.run_report run <place-id> --approve CODE [--repeats 3] [--again]   # PAID
    python -m src.run_report plan <place-id> --like <test-id> [--like <test-id>]    # a re-test of earlier tests
    python -m src.run_report status <place-id>              # read-only

Settings: DATABASE_URL as for the app (.env); API keys and models from the environment or the
app's ignored .streamlit/secrets.toml. Brief files hold client details: keep them outside this
public repository (docs/report-runner.md). Writes are recorded with created_by = "report_runner".
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Sequence

from src import report_runner as runner


def _records() -> list[dict[str, Any]]:
    from src.report_business_records import load_business_records

    return load_business_records()


def _business(place_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in records:
        if str(record.get("google_place_id")) == place_id:
            return record
    raise runner.PlanError(
        f"No business with Place ID {place_id} is in the database. Import its Outscraper record in Data Admin first."
    )


def _latest(place_id: str) -> dict[str, Any] | None:
    from src.report_audit_repository import get_latest_report_audit

    return get_latest_report_audit(place_id)


def cmd_find(args: argparse.Namespace) -> int:
    from src.business_lookup import near_misses, search_businesses

    records = _records()
    matches = search_businesses(records, args.query, limit=10)
    if not matches:
        print(f"No business matches “{args.query}”.")
        misses = near_misses(records, args.query)
        if misses:
            print("Did you mean: " + "; ".join(str(m.get("business_name")) for m in misses))
        print("A business that is not in the database must be imported in Data Admin before a report.")
        return 1
    for record in matches:
        print(
            f"{record.get('google_place_id')}  {record.get('business_name')}  "
            f"[{record.get('primary_group') or '-'}]  {record.get('address') or record.get('city') or ''}"
        )
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    brief = runner.load_brief(args.file)
    business = _business(brief.google_place_id, _records())
    saved = _latest(brief.google_place_id)
    print(f"Business: {business.get('business_name')} ({brief.google_place_id})")
    if str(business.get("business_name") or "").casefold() != brief.business_name.casefold():
        print(f"Note: the brief calls it “{brief.business_name}”; the listing name is kept for the report.")
    print(f"Questions ({len(brief.questions)}), each with its label and search intent:")
    for i, q in enumerate(brief.questions, start=1):
        print(f"  {i}. {runner.describe_question(q)}")
    changes = runner.brief_changes(brief, saved)
    if not changes:
        print("The saved brief already matches this file. Nothing to save.")
        return 0
    print("Would change: " + ", ".join(changes))
    at_risk = runner.current_work_at_risk(saved)
    if at_risk:
        print("Saving makes this no longer current (it is kept, and can be restored in step 1 of the page): "
              + "; ".join(at_risk))
    if not args.save:
        print("Read-only check. Add --save once the brief is approved.")
        return 0
    if at_risk and not args.replace_current:
        print("Not saved. Add --replace-current to save over current work.")
        return 2
    from src.report_audit_repository import save_owner_brief_revision

    arguments = brief.save_arguments()
    # The report uses the listing's own name, as the page does.
    arguments["target_business_name"] = str(business["business_name"])
    revision = save_owner_brief_revision(**arguments, created_by=runner.CREATED_BY)
    print(f"Saved as brief revision {revision['revision']}. Next: python -m src.run_report plan {brief.google_place_id}")
    return 0


def _resolve_run_id(place_id: str, given: str) -> str:
    """A test id, in full or by its first characters (as reports and notes quote it), for this business only."""

    from sqlalchemy import text

    from src.database import get_engine

    prefix = str(given or "").strip().lower()
    if len(prefix) < 8:
        raise runner.PlanError(f"Give at least the first 8 characters of the test id (got “{given}”)")
    with get_engine().connect() as connection:
        ids = connection.execute(
            text("select id::text from ai_visibility_runs where target_google_place_id = :place "
                 "and id::text like :prefix order by created_at"),
            {"place": place_id, "prefix": prefix + "%"},
        ).scalars().all()
    if not ids:
        raise runner.PlanError(f"No test of this business starts with {given}")
    if len(ids) > 1:
        raise runner.PlanError(f"Several tests start with {given}; give more of the id")
    return ids[0]


def _baseline(place_id: str, given_ids: list[str]) -> runner.Baseline:
    from src.ai_visibility_repository import get_run_queries, get_visibility_run
    from src.evidence_foundations_repository import load_measurement_wave

    runs = []
    for given in given_ids:
        run_id = _resolve_run_id(place_id, given)
        wave = load_measurement_wave(run_id) or {}
        runs.append((get_visibility_run(run_id), get_run_queries(run_id).to_dict("records"), wave.get("panel_kind")))
    return runner.baseline_from_runs(place_id, runs)


def _plan(args: argparse.Namespace) -> tuple[runner.RunPlan, dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    records = _records()
    business = _business(args.place_id, records)
    saved = _latest(args.place_id)
    settings = runner.load_settings()
    baseline = _baseline(args.place_id, args.like) if args.like else None
    plan = runner.plan_run(saved=saved, business=business, settings=settings, repeats=args.repeats, baseline=baseline)
    return plan, business, records, saved or {}, settings


def cmd_plan(args: argparse.Namespace) -> int:
    plan, *_ = _plan(args)
    print(runner.describe_plan(plan))
    extra = "".join(f" --like {r[:8]}" for r in plan.baseline_run_ids)
    if args.repeats is not None:
        extra += f" --repeats {args.repeats}"
    print("Nothing has been paid for. To run it once approved: "
          f"python -m src.run_report run {plan.google_place_id} --approve {plan.approval_code}{extra}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan, business, records, saved, settings = _plan(args)
    deps = runner.default_run_deps()
    runner.check_approval(plan, args.approve, again=args.again, deps=deps)
    print(f"Running {plan.call_count} paid calls for {plan.business_name}…")

    def progress(done: int, total: int) -> None:
        print(f"  {done} of {total} calls", end="\r", flush=True)

    outcome = runner.execute_plan(
        plan, business=business, business_records=records, settings=settings, saved=saved, deps=deps,
        progress=progress,
    )
    print()
    print(f"Test {outcome.run_id}: {outcome.status}")
    print(outcome.message)
    return 0 if outcome.attached else 3


def cmd_status(args: argparse.Namespace) -> int:
    saved = _latest(args.place_id)
    run = None
    if saved and saved.get("benchmark_run_id"):
        from src.ai_visibility_repository import get_visibility_run

        run = get_visibility_run(str(saved["benchmark_run_id"]))
    print(runner.describe_status(saved, run))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.run_report", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("find", help="Find a business's Google listing (read-only)")
    find.add_argument("query")
    find.set_defaults(func=cmd_find)

    brief = sub.add_parser("brief", help="Check a brief file, and save it with --save")
    brief.add_argument("file")
    brief.add_argument("--save", action="store_true", help="Save the brief as a new revision (gate 1 approved)")
    brief.add_argument("--replace-current", action="store_true",
                       help="Allow saving over an attached test or saved review decisions")
    brief.set_defaults(func=cmd_brief)

    for name, func, help_text in (
        ("plan", cmd_plan, "Show the paid test and its approval code (read-only)"),
        ("run", cmd_run, "Run the approved paid test and attach it (PAID)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("place_id")
        p.add_argument("--repeats", type=int, default=None, choices=(1, 2, 3),
                       help="Default 3, or the baseline's for a re-test")
        p.add_argument("--like", action="append", default=[], metavar="TEST_ID",
                       help="Re-test: repeat this earlier test's questions, location and repeats (repeatable)")
        if name == "run":
            p.add_argument("--approve", required=True, help="The approval code printed by plan")
            p.add_argument("--again", action="store_true", help="Pay for a new test even though one is attached")
        p.set_defaults(func=func)

    status = sub.add_parser("status", help="Where a report stands and what comes next (read-only)")
    status.add_argument("place_id")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (runner.BriefError, runner.PlanError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
