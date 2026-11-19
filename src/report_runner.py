"""Run a client report's setup and paid AI Visibility test without the Streamlit screens.

The report generator page (`app/pages/10_AI_Report_Generator.py`) and this module share the same
building blocks: the owner brief is saved by `save_owner_brief_revision`, the paid test is created,
called, finalised and attached by the same `ai_visibility_repository` / `ai_visibility_runner` /
`report_audit_repository` functions, and the prompt records and call plan come from the helpers
below, which the page also uses. Nothing here counts, matches names or writes report wording.

Three things are deliberately enforced in code rather than left to the operator:

- A brief only replaces the current one with `replace_current=True` when the business already has a
  test attached or review decisions saved, because a new brief makes that work no longer current
  (it is kept, and can be restored from step 1 of the page).
- A paid test needs an approval code that matches the plan shown to the person approving it. The
  code is a fingerprint of the saved brief revision, questions, repeats, tools, models and location,
  so a changed plan cannot run under an old approval.
- A test is not paid for twice: when a completed test is already attached, `again=True` is required.

A re-test (`Baseline`) copies the exact questions, customer location and repeats of one or more earlier
completed core tests of the same business, rather than rebuilding them from the saved brief, and its plan
lists anything that is no longer like-for-like (a changed model, changed repeats, a question that names
no place asked before the 10 November 2026 Claude location fix).

The command line is `src/run_report.py`; `docs/report-runner.md` describes the workflow.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from src.report_competitors import resolve_run_location
from src.report_generator_readiness import normalise_owner_brief, owner_brief_missing_fields

# One paid test may hold this many questions. Only listed questions run; nothing fills the list up to it.
MAX_RUN_QUESTIONS = 20
# The same three tools and default models as the operator pages and the free-check worker.
PROVIDERS = ("OpenAI", "Claude", "Gemini")
DEFAULT_MODELS = {
    "OpenAI": "gpt-5.6-terra",
    "Claude": "claude-sonnet-5",
    "Gemini": "gemini-3.6-flash",
}
KEY_NAMES = {"OpenAI": "OPENAI_API_KEY", "Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}
MODEL_NAMES = {"OpenAI": "OPENAI_MODEL", "Claude": "ANTHROPIC_MODEL", "Gemini": "GEMINI_MODEL"}
REPORT_INTENTS = ("discovery", "comparison", "transactional", "branded")
RATINGS = ("Not rated", "1", "2", "3", "4", "5")
# Must equal anthropic_provider.REQUIRED_SEARCH_VERSION, as the three paid-run pages check.
EXPECTED_SEARCH_VERSION = 3
CREATED_BY = "report_runner"
# Claude was told the customer's location in its instructions from this date (AGENTS.md, "How each AI tool is
# told the customer's location"). Its earlier answers to questions that name no place are not comparable.
CLAUDE_LOCATION_FIX = date(2026, 11, 10)
# Words in a location that do not, on their own, place a question.
_NOT_A_PLACE = {"and", "east", "west", "north", "south", "sussex", "the", "near"}
FINAL_BETA_COMPARISON_NOTE = (
    "In Final Beta, tick 'Compare with the earlier test' and choose these baselines under 'Earlier tests to compare "
    "with'. Left empty, it compares with the most recent earlier test sharing a question, which may be a later "
    "internal check."
)


# ---------------------------------------------------------------------------------------------
# Shared with the report generator page
# ---------------------------------------------------------------------------------------------


def prompt_records(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The paid test's prompt records, from question rows as the page's question table holds them.

    Each row has `question` and optionally `intent`, `report_intent`, `report_importance` and
    `report_effort`. Blank questions are dropped.
    """

    records = []
    for row in rows:
        question = str(row.get("question") or "").strip()
        if not question:
            continue
        records.append(
            {
                "category": str(row.get("intent") or "Owner priority"),
                "source": "owner_brief",
                "prompt": question,
                "report_intent": str(row.get("report_intent") or "discovery"),
                "report_importance": row.get("report_importance"),
                "report_effort": row.get("report_effort"),
            }
        )
    return records


def build_call_plan(query_records: Iterable[Mapping[str, Any]], providers: Iterable[str]) -> list[dict[str, Any]]:
    """One call per saved query (question x repeat) per AI tool, in the page's order."""

    providers = list(providers)
    return [{**query_record, "provider": provider} for query_record in query_records for provider in providers]


# ---------------------------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------------------------


def load_settings(
    environ: Mapping[str, str] = os.environ, secrets_path: str | Path = ".streamlit/secrets.toml"
) -> dict[str, Any]:
    """API keys and models: the environment first, then the app's ignored secrets file.

    Keys are never printed. A missing secrets file is not an error.
    """

    secrets: dict[str, Any] = {}
    path = Path(secrets_path)
    if path.is_file():
        with path.open("rb") as handle:
            secrets = tomllib.load(handle)

    def value(name: str, default: str = "") -> str:
        return str(environ.get(name) or secrets.get(name) or default).strip()

    return {
        "api_keys": {p: value(KEY_NAMES[p]) for p in PROVIDERS},
        "models": {p: value(MODEL_NAMES[p], DEFAULT_MODELS[p]) for p in PROVIDERS},
    }


def connected_providers(settings: Mapping[str, Any]) -> list[str]:
    return [p for p in PROVIDERS if settings["api_keys"].get(p)]


# ---------------------------------------------------------------------------------------------
# The brief file
# ---------------------------------------------------------------------------------------------


@dataclass
class Brief:
    google_place_id: str
    business_name: str
    known_for: str
    questions: list[dict[str, Any]]
    priority_services: list[str] = field(default_factory=list)
    service_areas: list[str] = field(default_factory=list)
    owner_competitors: list[str] = field(default_factory=list)
    ideal_customers: str = ""
    exclusions: list[str] = field(default_factory=list)
    additional_context: str = ""
    website: str = ""

    def save_arguments(self) -> dict[str, str]:
        """Keyword arguments for `save_owner_brief_revision`, in the page form's own shape."""

        return {
            "target_google_place_id": self.google_place_id,
            "target_business_name": self.business_name,
            "known_for": self.known_for,
            "desired_searches": "\n".join(q["question"] for q in self.questions),
            "owner_competitors": "\n".join(self.owner_competitors),
            "priority_services": "\n".join(self.priority_services),
            "service_areas": "\n".join(self.service_areas),
            "ideal_customers": self.ideal_customers,
            "exclusions": "\n".join(self.exclusions),
            "additional_context": self.additional_context,
            "manual_website_url": self.website,
            "question_details": self.question_details(),
        }

    def question_details(self) -> list[dict[str, Any]]:
        """Each question's label, search intent, importance and effort, saved with the brief."""

        return [
            {"question": q["question"], "label": q["intent"], "report_intent": q["report_intent"],
             "report_importance": q["report_importance"], "report_effort": q["report_effort"]}
            for q in self.questions
        ]


class BriefError(ValueError):
    """The brief file cannot be used as written. The message says what to fix."""


def _text_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BriefError(f"`{name}` must be a list of text lines")
    return [" ".join(item.split()) for item in value if item.strip()]


def _question(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, str):
        item = {"question": item}
    if not isinstance(item, dict):
        raise BriefError(f"Question {index} must be text or a table with `question`")
    question = " ".join(str(item.get("question") or "").split())
    if not question:
        raise BriefError(f"Question {index} has no wording")
    intent = str(item.get("search_intent") or "discovery").strip()
    if intent not in REPORT_INTENTS:
        raise BriefError(f"Question {index}: `search_intent` must be one of {', '.join(REPORT_INTENTS)}")
    rated = {}
    for key in ("importance", "effort"):
        rating = str(item.get(key) or "Not rated").strip()
        if rating not in RATINGS:
            raise BriefError(f"Question {index}: `{key}` must be 1 to 5, or left out")
        rated[key] = rating
    return {
        "question": question,
        "intent": " ".join(str(item.get("label") or "Owner priority").split()),
        "report_intent": intent,
        "report_importance": rated["importance"],
        "report_effort": rated["effort"],
    }


def parse_brief(data: Mapping[str, Any]) -> Brief:
    """Validate a brief read from TOML. Every problem is reported before anything is saved."""

    business = data.get("business")
    if not isinstance(business, dict):
        raise BriefError("The brief needs a [business] table with google_place_id and name")
    place_id = str(business.get("google_place_id") or "").strip()
    name = " ".join(str(business.get("name") or "").split())
    if not place_id:
        raise BriefError("`business.google_place_id` is required. Find it with: python -m src.run_report find \"<name>\"")
    if place_id.startswith("discovery:"):
        raise BriefError("A report needs a confirmed Google listing, not a `discovery:` placeholder")
    if not name:
        raise BriefError("`business.name` is required")
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise BriefError("The brief needs at least one entry in `questions`")
    questions = [_question(item, i) for i, item in enumerate(raw_questions, start=1)]
    if len(questions) > MAX_RUN_QUESTIONS:
        raise BriefError(f"One test holds at most {MAX_RUN_QUESTIONS} questions; this brief has {len(questions)}")
    seen: set[str] = set()
    for q in questions:
        key = q["question"].casefold()
        if key in seen:
            raise BriefError(f"The question “{q['question']}” is listed twice")
        seen.add(key)
    brief = Brief(
        google_place_id=place_id,
        business_name=name,
        known_for=" ".join(str(data.get("known_for") or "").split()),
        questions=questions,
        priority_services=_text_list(data.get("priority_services"), "priority_services"),
        service_areas=_text_list(data.get("service_areas"), "service_areas"),
        owner_competitors=_text_list(data.get("owner_competitors"), "owner_competitors"),
        ideal_customers=" ".join(str(data.get("ideal_customers") or "").split()),
        exclusions=_text_list(data.get("exclusions"), "exclusions"),
        additional_context=" ".join(str(data.get("additional_context") or "").split()),
        website=str(business.get("website") or "").strip(),
    )
    # The same completeness rule the page applies before saving.
    missing = owner_brief_missing_fields(
        normalise_owner_brief(
            known_for=brief.known_for,
            desired_searches="\n".join(q["question"] for q in questions),
            owner_competitors="\n".join(brief.owner_competitors),
        )
    )
    if missing:
        raise BriefError("Please complete: " + "; ".join(missing))
    if brief.website and not brief.website.startswith(("http://", "https://")):
        raise BriefError("`business.website` must begin with http:// or https://")
    return brief


def load_brief(path: str | Path) -> Brief:
    path = Path(path)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise BriefError(f"No brief file at {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise BriefError(f"The brief file is not valid TOML: {exc}") from exc
    return parse_brief(data)


def saved_question_rows(saved: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The saved brief's questions as question rows, with any label, intent and importance saved beside them.

    A question saved without details (as the page saves a brief) gets the page's defaults.
    """

    details = {
        " ".join(str(d.get("question") or "").split()).casefold(): d
        for d in list(dict(saved.get("owner_context") or {}).get("question_details") or [])
    }
    rows = []
    for question in list(saved.get("desired_searches") or []):
        detail = details.get(" ".join(str(question).split()).casefold(), {})
        rows.append({
            "question": question,
            "intent": str(detail.get("label") or "Owner priority"),
            "report_intent": str(detail.get("report_intent") or "discovery"),
            "report_importance": detail.get("report_importance"),
            "report_effort": detail.get("report_effort"),
        })
    return rows


def describe_question(record: Mapping[str, Any]) -> str:
    """One question as the brief check and the plan show it: wording, then label, intent and ratings."""

    parts = [str(record.get("category") or record.get("intent") or "Owner priority"),
             str(record.get("report_intent") or "discovery")]
    for name in ("importance", "effort"):
        value = record.get(f"report_{name}")
        if value not in (None, "", "Not rated"):
            parts.append(f"{name} {value}")
    prompt = record.get("prompt") or record.get("question")
    return f"{prompt}  [{' · '.join(parts)}]"


def _detail_key(question: Any, label: Any, intent: Any, importance: Any, effort: Any) -> tuple[str, ...]:
    """A question's details for comparison, with a missing rating read as "Not rated"."""

    return (" ".join(str(question).split()).casefold(), str(label or "Owner priority"), str(intent or "discovery"),
            str(importance or "Not rated"), str(effort or "Not rated"))


def brief_changes(brief: Brief, saved: Mapping[str, Any] | None) -> list[str]:
    """What saving this brief would change compared with the saved revision, in plain words."""

    if not saved:
        return ["first brief for this business"]
    context = dict(saved.get("owner_context") or {})
    changes = []
    comparisons = (
        ("what it should be known for", brief.known_for, str(saved.get("known_for") or "")),
        ("questions", [q["question"] for q in brief.questions], list(saved.get("desired_searches") or [])),
        ("named competitors", brief.owner_competitors, list(saved.get("owner_competitors") or [])),
        ("priority services", brief.priority_services, list(context.get("priority_services") or [])),
        ("service areas", brief.service_areas, list(context.get("service_areas") or [])),
        ("ideal customers", brief.ideal_customers, str(context.get("ideal_customers") or "")),
        ("not to promote", brief.exclusions, list(context.get("exclusions") or [])),
        ("other context", brief.additional_context, str(context.get("additional_context") or "")),
        ("website", brief.website, str(saved.get("manual_website_url") or "")),
        ("question labels, intents or ratings",
         [_detail_key(q["question"], q["intent"], q["report_intent"], q["report_importance"], q["report_effort"])
          for q in brief.questions],
         [_detail_key(r["question"], r["intent"], r["report_intent"], r["report_importance"], r["report_effort"])
          for r in saved_question_rows(saved)]),
    )
    for label, new, old in comparisons:
        if new != old:
            changes.append(label)
    return changes


def current_work_at_risk(saved: Mapping[str, Any] | None) -> list[str]:
    """Work on the current revision that a new brief would make no longer current."""

    if not saved:
        return []
    risks = []
    if saved.get("benchmark_run_id"):
        risks.append(f"the attached AI Visibility test {saved['benchmark_run_id']}")
    if dict(saved.get("reviewer_decisions") or {}):
        risks.append("the saved review decisions" + (" (review complete)" if saved.get("reviewer_decisions_complete") else ""))
    return risks


# ---------------------------------------------------------------------------------------------
# The paid test plan and its approval code
# ---------------------------------------------------------------------------------------------


class PlanError(ValueError):
    """A paid test cannot start. The message says what to fix."""


@dataclass(frozen=True)
class Baseline:
    """The earlier test(s) a re-test repeats: their exact questions, location and repeats."""

    run_ids: tuple[str, ...]
    run_dates: tuple[date, ...]
    location: str
    repeats: int
    models: tuple[tuple[str, str], ...]
    rows: tuple[dict[str, Any], ...]
    notes: tuple[str, ...] = ()


def _run_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value if not hasattr(value, "date") else value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def baseline_from_runs(
    place_id: str, runs: Iterable[tuple[Mapping[str, Any], Iterable[Mapping[str, Any]], str | None]]
) -> Baseline:
    """Check earlier tests can be repeated together, and take their questions in their original order.

    Each item is (saved run, its saved queries, its panel kind or None). Runs must be completed core tests of
    this business with one customer location and one number of repeats.
    """

    runs = list(runs)
    if not runs:
        raise PlanError("Name at least one earlier test to repeat")
    run_ids, dates, locations, repeats, models, rows, notes = [], [], set(), set(), [], [], []
    seen: dict[str, str] = {}
    for run, queries, panel_kind in runs:
        run_id = str(run.get("id") or "")
        if not run_id:
            raise PlanError("An earlier test named for the re-test was not found")
        short = run_id[:8]
        if str(run.get("target_google_place_id") or "") != place_id:
            raise PlanError(f"Test {short} is of a different business")
        if str(run.get("status") or "") != "completed":
            raise PlanError(f"Test {short} is '{run.get('status')}', not completed, so it cannot be a baseline")
        if panel_kind not in (None, "", "core"):
            raise PlanError(f"Test {short} is a {panel_kind} run, not a client test, so it cannot be a baseline")
        run_ids.append(run_id)
        dates.append(_run_date(run.get("started_at") or run.get("created_at")))
        locations.add(str(run.get("location_context") or ""))
        repeats.add(int(run.get("repeat_count") or 1))
        models.append(tuple(sorted(dict(run.get("models") or {}).items())))
        ordered = sorted(queries, key=lambda q: (int(q.get("base_prompt_order") or 0), int(q.get("repeat_index") or 0),
                                                 int(q.get("prompt_order") or 0)))
        for query in ordered:
            text = str(query.get("prompt_text") or "").strip()
            key = text.casefold()
            if not text:
                continue
            if key in seen:
                if seen[key] != short:
                    notes.append(f"“{text}” was asked in both {seen[key]} and {short}; it is asked once.")
                continue
            seen[key] = short
            rows.append({
                "question": text,
                "intent": str(query.get("prompt_category") or "Owner priority"),
                "report_intent": str(query.get("report_intent") or "discovery"),
                "report_importance": query.get("report_importance"),
                "report_effort": query.get("report_effort"),
            })
    if len(locations) != 1 or not next(iter(locations)):
        raise PlanError("The earlier tests told the AI tools different customer locations ("
                        + "; ".join(sorted(f"“{l}”" for l in locations)) + "), so they cannot be repeated as one test")
    if len(repeats) != 1:
        raise PlanError("The earlier tests used different numbers of repeats, so they cannot be repeated as one test")
    if len(set(models)) != 1:
        notes.append("The earlier tests did not all use the same models.")
    if not rows:
        raise PlanError("The earlier tests have no saved questions")
    if len(rows) > MAX_RUN_QUESTIONS:
        raise PlanError(f"Together the earlier tests hold {len(rows)} questions; one test holds at most {MAX_RUN_QUESTIONS}")
    return Baseline(
        run_ids=tuple(run_ids),
        run_dates=tuple(d for d in dates if d),
        location=next(iter(locations)),
        repeats=next(iter(repeats)),
        models=models[0],
        rows=tuple(rows),
        notes=tuple(notes),
    )


def names_a_place(question: str, location: str) -> bool:
    """Whether the question names any place word from the location ("Brighton", "Hove")."""

    words = {w for w in re.findall(r"[a-z]+", location.casefold()) if len(w) >= 3 and w not in _NOT_A_PLACE}
    asked = set(re.findall(r"[a-z]+", question.casefold()))
    return bool(words & asked)


def retest_warnings(baseline: Baseline, *, models: Mapping[str, str], repeats: int,
                    saved_questions: Iterable[str]) -> list[str]:
    """What makes a re-test less than like-for-like, in plain words."""

    warnings = list(baseline.notes)
    for provider, model in baseline.models:
        if provider in models and models[provider] != model:
            warnings.append(f"{provider} now uses {models[provider]}; the baseline used {model}.")
    if repeats != baseline.repeats:
        warnings.append(f"Each question is asked {repeats} times; the baseline asked it {baseline.repeats} times.")
    early = any(d < CLAUDE_LOCATION_FIX for d in baseline.run_dates)
    for row in baseline.rows:
        if not names_a_place(row["question"], baseline.location):
            if early:
                warnings.append(f"“{row['question']}” names no place, and the baseline was before the "
                                f"{CLAUDE_LOCATION_FIX:%-d %B %Y} Claude location fix: Claude's answers to it are not comparable.")
            else:
                warnings.append(f"“{row['question']}” names no place: its answers rest on the location setting alone.")
    saved = {q.casefold() for q in saved_questions}
    if saved and saved != {r["question"].casefold() for r in baseline.rows}:
        warnings.append("The saved brief's questions differ from the baseline's. The re-test asks the baseline's.")
    warnings.append(FINAL_BETA_COMPARISON_NOTE)
    return warnings


@dataclass(frozen=True)
class RunPlan:
    google_place_id: str
    business_name: str
    revision: int
    revision_id: str
    location: str
    questions: tuple[str, ...]
    prompts: tuple[dict[str, Any], ...]
    repeats: int
    providers: tuple[str, ...]
    models: tuple[tuple[str, str], ...]
    attached_run_id: str
    baseline_run_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def call_count(self) -> int:
        return len(self.prompts) * self.repeats * len(self.providers)

    @property
    def approval_code(self) -> str:
        """A short fingerprint of exactly what will be paid for."""

        payload = json.dumps(
            {
                "place": self.google_place_id,
                "revision_id": self.revision_id,
                "location": self.location,
                "prompts": list(self.prompts),
                "repeats": self.repeats,
                "providers": list(self.providers),
                "models": [list(m) for m in self.models],
                "baseline": list(self.baseline_run_ids),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8].upper()


def plan_run(
    *,
    saved: Mapping[str, Any] | None,
    business: Mapping[str, Any],
    settings: Mapping[str, Any],
    repeats: int | None = None,
    rows: Iterable[Mapping[str, Any]] | None = None,
    baseline: Baseline | None = None,
) -> RunPlan:
    """The paid test the saved brief asks for, or a PlanError naming what blocks it.

    `rows` are the question rows to run; by default every saved question, labelled as the page does. With a
    `baseline`, the questions, customer location and (unless `repeats` is given) repeats are the baseline's.
    """

    if not saved:
        raise PlanError("No brief is saved for this business. Save one first: python -m src.run_report brief <file> --save")
    if owner_brief_missing_fields({"known_for": saved.get("known_for"), "desired_searches": saved.get("desired_searches")}):
        raise PlanError("The saved brief is incomplete. Save a complete brief first.")
    if repeats is None:
        repeats = baseline.repeats if baseline else 3
    if repeats not in (1, 2, 3):
        raise PlanError("Repeats must be 1, 2 or 3")
    if baseline is not None:
        rows = baseline.rows
    elif rows is None:
        rows = saved_question_rows(saved)
    prompts = prompt_records(rows)
    if not prompts:
        raise PlanError("No questions to run")
    if len(prompts) > MAX_RUN_QUESTIONS:
        raise PlanError(f"One test holds at most {MAX_RUN_QUESTIONS} questions")
    providers = connected_providers(settings)
    missing = [p for p in PROVIDERS if p not in providers]
    if missing:
        raise PlanError("Connect all three AI tools before running: " + ", ".join(missing) + " has no API key")
    context = dict(saved.get("owner_context") or {})
    if baseline is not None:
        location = baseline.location  # exactly as the baseline told the AI tools, not rebuilt from the brief
    else:
        location = resolve_run_location(context.get("service_areas") or [], business.get("city"))
    if not location:
        raise PlanError(
            "This business has no city on record and the brief has no service area, so the AI tools would not know "
            "where the customer is searching from. Add `service_areas` to the brief."
        )
    return RunPlan(
        google_place_id=str(saved["target_google_place_id"]),
        business_name=str(saved.get("target_business_name") or business.get("business_name") or ""),
        revision=int(saved.get("revision") or 0),
        revision_id=str(saved.get("id") or ""),
        location=location,
        questions=tuple(p["prompt"] for p in prompts),
        prompts=tuple(prompts),
        repeats=int(repeats),
        providers=tuple(providers),
        models=tuple((p, str(settings["models"][p])) for p in providers),
        attached_run_id=str(saved.get("benchmark_run_id") or ""),
        baseline_run_ids=baseline.run_ids if baseline else (),
        warnings=tuple(
            retest_warnings(baseline, models=settings["models"], repeats=int(repeats),
                            saved_questions=list(saved.get("desired_searches") or []))
        ) if baseline else (),
    )


def describe_plan(plan: RunPlan) -> str:
    lines = [
        f"Business: {plan.business_name} ({plan.google_place_id})",
        f"Brief revision: {plan.revision}",
        *([f"Re-test of: {', '.join(r[:8] for r in plan.baseline_run_ids)} (same questions, location and repeats)"]
          if plan.baseline_run_ids else []),
        f"Customer location given to the AI tools: {plan.location}",
        f"Questions ({len(plan.prompts)}), each with its label and search intent:",
        *[f"  {i}. {describe_question(p)}" for i, p in enumerate(plan.prompts, start=1)],
        f"Each question {plan.repeats} times on {', '.join(f'{p} ({m})' for p, m in plan.models)}",
        f"Paid API calls: {plan.call_count}. Live web search is on, so search-tool charges may also apply.",
    ]
    if plan.attached_run_id:
        lines.append(f"Note: a test is already attached to this brief ({plan.attached_run_id}).")
    if plan.warnings:
        lines.append("Read before approving:")
        lines.extend(f"  - {w}" for w in plan.warnings)
    lines.append(f"Approval code: {plan.approval_code}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------------------------


@dataclass
class RunDeps:
    """The functions a paid test uses. Tests replace them; nothing here pays by default in tests."""

    create_visibility_run: Callable[..., str]
    create_visibility_queries: Callable[..., list[dict[str, Any]]]
    execute_calls: Callable[..., Any]
    finalise_run_from_results: Callable[..., str]
    attach_benchmark_revision: Callable[..., dict[str, Any]]
    get_visibility_run: Callable[[str], dict[str, Any]]
    search_version: int


def default_run_deps() -> RunDeps:
    import src.ai_visibility_repository as repository
    import src.ai_visibility_runner as runner
    import src.llm_providers.anthropic_provider as anthropic_provider
    import src.report_audit_repository as audits

    return RunDeps(
        create_visibility_run=repository.create_visibility_run,
        create_visibility_queries=repository.create_visibility_queries,
        execute_calls=runner.execute_calls,
        finalise_run_from_results=runner.finalise_run_from_results,
        attach_benchmark_revision=audits.attach_benchmark_revision,
        get_visibility_run=repository.get_visibility_run,
        search_version=int(getattr(anthropic_provider, "REQUIRED_SEARCH_VERSION", 0)),
    )


@dataclass
class RunOutcome:
    run_id: str
    status: str
    attached: bool
    message: str


def check_approval(
    plan: RunPlan, approval: str, *, again: bool, deps: RunDeps
) -> None:
    """Raise PlanError unless this exact plan was approved and nothing would be paid for twice."""

    if deps.search_version != EXPECTED_SEARCH_VERSION:
        raise PlanError(
            "The AI search code has changed (search version "
            f"{deps.search_version}, expected {EXPECTED_SEARCH_VERSION}). Update EXPECTED_SEARCH_VERSION here "
            "with the matching page guards before running."
        )
    if str(approval or "").strip().upper() != plan.approval_code:
        raise PlanError(
            "The approval code does not match this plan. Show the plan again (python -m src.run_report plan ...), "
            "get it approved, and use the code it prints."
        )
    if plan.attached_run_id and not again:
        attached = deps.get_visibility_run(plan.attached_run_id)
        if str(attached.get("status") or "") == "completed":
            raise PlanError(
                f"A completed test is already attached to this brief ({plan.attached_run_id}). "
                "Running again pays for a new one; add --again only if that is intended."
            )


def execute_plan(
    plan: RunPlan,
    *,
    business: Mapping[str, Any],
    business_records: Iterable[Mapping[str, Any]],
    settings: Mapping[str, Any],
    saved: Mapping[str, Any],
    deps: RunDeps,
    progress: Callable[[int, int], None] | None = None,
    status: Callable[[str], None] | None = None,
) -> RunOutcome:
    """Create, call, finalise and attach the paid test, exactly as the page's step 3 does."""

    models = dict(plan.models)
    prompts = [dict(p) for p in plan.prompts]
    providers = list(plan.providers)
    run_id = deps.create_visibility_run(
        prompts=prompts,
        target_propositions=list(dict(saved.get("owner_context") or {}).get("priority_services") or []),
        target_google_place_id=plan.google_place_id,
        target_business_name=str(business.get("business_name") or plan.business_name),
        primary_group=str(business.get("primary_group") or "generic"),
        location_context=plan.location,
        providers=providers,
        models=models,
        prompt_count=len(prompts),
        repeat_count=plan.repeats,
    )
    query_records = deps.create_visibility_queries(run_id=run_id, prompts=prompts, repetitions=plan.repeats)
    call_plan = build_call_plan(query_records, providers)
    deps.execute_calls(
        run_id=run_id,
        call_plan=call_plan,
        models=models,
        api_keys={p: settings["api_keys"][p] for p in providers},
        target_google_place_id=plan.google_place_id,
        target_business_name=str(business.get("business_name") or plan.business_name),
        known_businesses=[
            {"google_place_id": str(item["google_place_id"]), "business_name": str(item["business_name"])}
            for item in business_records
        ],
        benchmark_mode="search_grounded",
        location_context=plan.location,
        progress_callback=progress,
        status_callback=status,
    )
    run_status = deps.finalise_run_from_results(run_id=run_id, expected_call_count=len(call_plan))
    if run_status != "completed":
        return RunOutcome(
            run_id=run_id,
            status=run_status,
            attached=False,
            message=(
                f"The test finished as '{run_status}', so it was not attached. Saved answers are kept. Retry only the "
                "missing calls on the AI Visibility page (Resume/retry), then attach it from step 2 of the report "
                "generator (Use an already-completed AI Visibility run)."
            ),
        )
    deps.attach_benchmark_revision(
        target_google_place_id=plan.google_place_id, benchmark_run_id=run_id, created_by=CREATED_BY
    )
    message = ("The test is complete and attached. Next: website and review evidence (step 4) and the review "
               "(step 5) in the report generator.")
    if plan.baseline_run_ids:
        message += (" For Final Beta, tick 'Compare with the earlier test' and choose "
                    + ", ".join(r[:8] for r in plan.baseline_run_ids) + " under 'Earlier tests to compare with'.")
    return RunOutcome(run_id=run_id, status=run_status, attached=True, message=message)


# ---------------------------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------------------------


def describe_status(saved: Mapping[str, Any] | None, run: Mapping[str, Any] | None) -> str:
    """Where a report stands and what comes next, from the saved revision alone (read-only)."""

    if not saved:
        return "No brief saved yet. Next: write the brief file and save it (brief <file> --save)."
    run_id = str(saved.get("benchmark_run_id") or "")
    run_status = str((run or {}).get("status") or "")
    lines = [
        f"{saved.get('target_business_name')} ({saved.get('target_google_place_id')})",
        f"Current revision: {saved.get('revision')} ({saved.get('revision_reason') or 'saved'}, by {saved.get('created_by')})",
        f"Questions saved: {len(list(saved.get('desired_searches') or []))}",
        f"Test attached: {run_id + ' (' + (run_status or 'unknown') + ')' if run_id else 'none'}",
        f"Website evidence: {saved.get('website_evidence_state') or 'not_checked'}; "
        f"review evidence: {saved.get('review_evidence_state') or 'not_checked'}",
        f"Review (step 5) complete: {'yes' if saved.get('reviewer_decisions_complete') else 'no'}",
    ]
    if not run_id:
        nxt = "show the plan (plan <place-id>), get it approved, then run it."
    elif run_status != "completed":
        nxt = "finish the attached test on the AI Visibility page before going further."
    elif not saved.get("reviewer_decisions_complete"):
        nxt = "add website and review evidence (step 4) and complete the review (step 5) in the report generator."
    else:
        nxt = "generate Final Beta in step 6 of the report generator."
    lines.append("Next: " + nxt)
    return "\n".join(lines)
