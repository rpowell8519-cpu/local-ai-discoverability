"""Recommendations grounded in what the client's own touchpoints show against the businesses doing well.

The reports' actions used to come from two narrow checks and generic advice by business type. This module
runs the analysis the earlier client work already relied on, and turns what it finds into candidates a
reviewer can approve:

* the client's saved website against the saved websites of the businesses the AI recommends most,
* whether each site covers what the owner wants to be known for (the owner's priorities), and
* what customers say in Google reviews, the client against those businesses.

Those engines (website_benchmark, ai_competitive_diagnostic, review_analysis, recommendation_synthesis)
decide what is worth acting on: a competitor difference is not automatically advice, and it only counts
when it is relevant, common among the leaders and within the client's control. This module keeps that
selection but words each candidate for the kind of business, states the numbers and names the leaders
behind it, and never says why something happened. Nothing is written by a model.

A "leader" is a business the AI actually recommended. A competitor the owner named that the AI never
recommended is not a leader, so it cannot make something look common among the businesses that are winning.
"""
from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from src.ai_competitive_diagnostic import build_proposition_benchmark, build_proposition_coverage
from src.client_summary.actions import profile_for
from src.recommendation_synthesis import build_recommendation_synthesis
from src.review_analysis import build_review_benchmark
from src.review_profiles import get_review_profile
from src.type_wording import to_audit_checks, to_profile, to_review_themes
from src.vertical_audit_profiles import get_audit_profile
from src.website_benchmark import USABLE_AUDIT_STATUSES, build_website_benchmark, evaluate_business

MAX_LEADERS = 5
LAYERS = ("website", "propositions", "reviews")
_PROPOSITION_TITLE = "Deepen crawlable content for "
_OWNER = "Business owner supplies the facts; website provider publishes them"
_HYGIENE_PENALTY = 30.0  # structured data is housekeeping: no measured effect on AI answers, so it ranks last


def select_leaders(
    candidates: Iterable[Mapping[str, Any]], target_id: str, *, limit: int = MAX_LEADERS
) -> list[dict[str, Any]]:
    """The businesses the AI actually recommended, most visible first, excluding the client."""

    visible = [
        dict(item) for item in candidates
        if str(item.get("google_place_id")) != str(target_id) and int(item.get("recommendations") or 0) > 0
    ]
    return sorted(visible, key=lambda item: (-int(item["recommendations"]), str(item.get("business_name"))))[:limit]


def _date(value: Any) -> str | None:
    try:
        return pd.Timestamp(value).date().isoformat() if value is not None and not pd.isna(value) else None
    except (ValueError, TypeError):
        return None


def _named(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def _covered_by_priority(label: str, propositions) -> bool:
    """Whether a website topic is one of the owner's own priorities (so it is not recommended twice)."""

    from src.ai_recommendation_intelligence import normalise_name
    wanted = normalise_name(label)
    return any(wanted and (wanted in normalise_name(p) or normalise_name(p) in wanted) for p in propositions or [])


def _unavailable(layers: dict[str, dict[str, Any]], key: str, why: str) -> None:
    layers[key] = {"status": "unavailable", "note": why}


# ---------------------------------------------------------------- wording, by signal and business type
def _website_wording(key: str, profile, label: str = "") -> dict[str, str] | None:
    """Action wording for a website signal, in the language of this kind of business."""

    if key.startswith("type_check_"):
        return {
            "title": f"Cover “{label}” on the website",
            "action": f"Add a page or clear section on “{label}”: what is offered, what a customer needs to know, and how to book or buy. "
                      "Use the words customers use and link it from the main navigation.",
            "done_when": f"A customer searching the site for “{label}” lands on a page that answers it, linked from the main navigation",
        }

    if key == "booking":
        return {
            "title": f"Make it obvious how to {profile.booking}",
            "action": f"Add a clear, visible way to {profile.booking} on the home page and the pages that cover each service, "
                      "and say the same in the page text as well as on the button.",
            "done_when": f"A customer can {profile.booking} from the home page in two clicks, and the team has tested that route",
        }
    if key in ("pricing", "services"):
        return {
            "title": f"Publish {profile.pricing} on the page for each service",
            "action": f"Show {profile.pricing} as ordinary page text next to each service, not only in images, PDFs or third-party "
                      "systems. Where an exact price varies, give a starting price or a range.",
            "done_when": f"Each service page shows {profile.pricing}, and it can be read without opening an image or a PDF",
        }
    if key == "faq":
        return {
            "title": "Answer the common questions on the site",
            "action": f"Add a short FAQ covering {profile.questions}, using the wording customers use. Include only answers the team can stand behind.",
            "done_when": "The FAQ is reachable from the main navigation, and each answer has been checked by the team",
        }
    if key == "relevant_schema":
        return {
            "title": "Add structured business data (housekeeping)",
            "action": "Ask the website provider to add LocalBusiness structured data that matches the details visible on the page. "
                      "This is housekeeping: there is no evidence that it changes AI answers.",
            "done_when": "The structured data validates and matches the visible name, address, phone number and opening times",
        }
    if key in ("contact", "address"):
        return {
            "title": "Make contact and address details easy to find",
            "action": "Show the phone number, address and opening times as text on every page's footer or header, matching the Google listing.",
            "done_when": "The same details appear in text on every page and match the Google listing",
        }
    return None


def _website_candidates(
    *, fb: pd.DataFrame, te: pd.DataFrame, evals: Mapping[str, Mapping[str, Any]], names: Mapping[str, str],
    reads: Mapping[str, dict[str, Any]], target_id: str, target_name: str, leader_ids: list[str], profile, layer_note: str,
    propositions: list[str] = (),
) -> list[dict[str, Any]]:
    recommended = {str(row["signal"]) for row in te.to_dict("records") if str(row.get("disposition")) == "Recommend"}
    scores = {str(row["signal"]): row for row in te.to_dict("records")}
    candidates = []
    for row in fb.to_dict("records"):
        label, key = str(row["check"]), str(row["key"])
        if label not in recommended or row.get("target_found"):
            continue
        if key.startswith("type_check_") and _covered_by_priority(label, propositions):
            continue  # the owner's own priority already gets its own recommendation
        wording = _website_wording(key, profile, label)
        if wording is None:
            continue
        having = [pid for pid in leader_ids if evals.get(pid, {}).get(key, {}).get("found")]
        found, size = len(having), int(row["cohort_size"])
        who = _named([names[pid] for pid in having])
        hygiene = key == "relevant_schema"
        score = float(scores[label].get("score") or 0) - (_HYGIENE_PENALTY if hygiene else 0)
        evidence = [{"business": target_name, "read_on": reads.get(target_id, {}).get("read_on"), "url": reads.get(target_id, {}).get("url"),
                     "note": f"“{label}” not detected on the saved pages"}]
        evidence += [{"business": names[pid], "read_on": reads.get(pid, {}).get("read_on"), "url": reads.get(pid, {}).get("url"),
                      "note": f"“{label}” detected"} for pid in having]
        candidates.append({
            "id": f"website:{key}", "kind": "action", "layer": "website", "signal": key, "title": wording["title"],
            "observation": f"{label} was not detected on {target_name}'s saved website pages, and was detected on {found} of {size} "
                           f"of the most visible businesses" + (f" ({who})." if who else "."),
            "why": f"{label} was not detected on your saved pages, but was on {found} of {size} of the most visible businesses.",
            "action": wording["action"], "done_when": wording["done_when"], "owner": _OWNER,
            "confidence": str(scores[label].get("confidence") or "Medium") if not hygiene else "Low",
            "score": round(score, 1), "prevalence": f"{found} of {size}", "evidence": evidence, "hygiene": hygiene, "basis": layer_note,
        })
    return candidates


def _proposition_candidates(
    *, actions: pd.DataFrame, pb: pd.DataFrame, cov: pd.DataFrame, names: Mapping[str, str], reads: Mapping[str, dict[str, Any]],
    target_id: str, target_name: str, profile, layer_note: str,
) -> list[dict[str, Any]]:
    candidates = []
    rows = {str(r["proposition"]): r for r in pb.to_dict("records")} if not pb.empty else {}
    for action in actions.to_dict("records"):
        title = str(action["title"])
        if not title.startswith(_PROPOSITION_TITLE):
            continue
        topic = title[len(_PROPOSITION_TITLE):]
        row = rows.get(topic)
        if row is None:
            continue
        having = [str(r["google_place_id"]) for r in cov.to_dict("records")
                  if str(r["proposition"]) == topic and str(r["google_place_id"]) != target_id and int(r["pages_mentioning"]) > 0]
        found, size = int(row["leaders_with_coverage"]), int(row["leader_count"])
        who = _named([names[pid] for pid in having if pid in names])
        evidence = [{"business": target_name, "read_on": reads.get(target_id, {}).get("read_on"), "url": reads.get(target_id, {}).get("url"),
                     "note": f"“{topic}” found on {int(row['target_pages'])} saved page(s)"}]
        evidence += [{"business": names[pid], "read_on": reads.get(pid, {}).get("read_on"), "url": reads.get(pid, {}).get("url"),
                      "note": f"“{topic}” covered on {next(int(r['pages_mentioning']) for r in cov.to_dict('records') if str(r['proposition']) == topic and str(r['google_place_id']) == pid)} saved page(s)"}
                     for pid in having if pid in names]
        candidates.append({
            "id": f"propositions:{topic.casefold()}", "kind": "action", "layer": "propositions", "signal": topic,
            "title": f"Give “{topic}” its own clear page or section",
            "observation": f"“{topic}” is one of the things the owner wants to be known for. It appears on {int(row['target_pages'])} of "
                           f"{target_name}'s saved pages, and on the saved pages of {found} of {size} of the most visible businesses"
                           + (f" ({who})." if who else "."),
            "why": f"You want to be known for “{topic}”, but it is on {int(row['target_pages'])} of your saved pages, and on {found} of {size} of the most visible businesses' sites.",
            "action": f"Add a page or clear section on “{topic}”: what is offered, {profile.pricing}, and how to {profile.booking}. Use the "
                      "words customers use, and link to it from the main navigation.",
            "done_when": f"A customer searching for “{topic}” lands on a page that says what is offered, {profile.pricing} and how to {profile.booking}",
            "owner": _OWNER, "confidence": str(action.get("confidence") or "Medium"), "score": round(float(action.get("score") or 0), 1),
            "prevalence": f"{found} of {size}", "evidence": evidence, "hygiene": False, "basis": layer_note,
        })
    return candidates


def _review_findings(*, rb: dict[str, Any], target_name: str, leader_ids: list[str], names: Mapping[str, str],
                     obs: pd.DataFrame) -> list[dict[str, Any]]:
    """Themes that customers of the most visible businesses mention more often than the client's do."""

    summaries = {str(r["google_place_id"]): r for r in rb["business_summaries"].to_dict("records")}
    target_n = next((int(r["reviews_analysed"]) for r in summaries.values() if str(r["business_name"]) == target_name), 0)
    leader_n = sum(int(summaries[pid]["reviews_analysed"]) for pid in leader_ids if pid in summaries)
    themes = {str(r["theme_label"]): r for r in rb["benchmark"].to_dict("records")} if hasattr(rb["benchmark"], "to_dict") else \
        {str(r["theme_label"]): r for r in rb["benchmark"]}
    findings = []
    for row in obs.to_dict("records"):
        if str(row.get("category")) != "Customer association":
            continue
        theme = str(row["title"]).split(": ", 1)[-1]
        numbers = themes.get(theme)
        if numbers is None:
            continue
        mine, theirs = round(float(numbers["target_pct"]) * 100), round(float(numbers["cohort_median_pct"]) * 100)
        findings.append({
            "id": f"reviews:{theme.casefold().replace(' ', '-').replace('/', '')}", "kind": "finding", "layer": "reviews", "signal": theme,
            "title": f"“{theme}” comes up less often in {target_name}'s reviews",
            "observation": f"“{theme}” came up in {mine}% of {target_name}'s {target_n} sampled reviews, against a median of {theirs}% for the most "
                           f"visible businesses ({leader_n} reviews). Themes are counted from keywords in a small sample, so read this as a prompt "
                           "to look at the touchpoint, not as a finding about cause.",
            "why": f"“{theme}” came up in {mine}% of your sampled reviews, against a median of {theirs}% for the most visible businesses.",
            "action": "", "done_when": "", "owner": "", "confidence": "Low", "score": 0.0, "prevalence": "", "evidence": [], "hygiene": False,
            "basis": f"Google review text: {target_n} of the client's reviews and {leader_n} reviews of the most visible businesses",
        })
    return findings


def _review_profile(primary_group: str, type_wording: Mapping[str, Any] | None) -> dict[str, Any]:
    """The review themes for the type, plus any a reviewer approved for a type with none of its own."""

    profile = get_review_profile(primary_group)
    extra = to_review_themes(type_wording)
    return {**profile, "themes": [*profile["themes"], *extra]} if extra else profile


def analyse_evidence(
    *,
    target_id: str,
    target_name: str,
    primary_group: str,
    leaders: list[Mapping[str, Any]],
    audits: pd.DataFrame,
    pages_by_run: Mapping[str, pd.DataFrame],
    propositions: list[str],
    reviews: pd.DataFrame,
    type_wording: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the engines on the client and its leaders and return candidate recommendations.

    Every layer degrades on its own: a missing site or review sample says so and never stops the others.
    """

    target_id = str(target_id)
    leader_ids = [str(item["google_place_id"]) for item in leaders]
    names = {target_id: target_name, **{str(item["google_place_id"]): str(item["business_name"]) for item in leaders}}
    profile = to_profile(type_wording, primary_group)
    layers: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    strengths: list[dict[str, Any]] = []
    reads: dict[str, dict[str, Any]] = {}
    website_ready = pb = cov = actions = te = None

    frame = audits.copy() if audits is not None and not audits.empty else pd.DataFrame()
    if not frame.empty:
        frame = frame[frame["google_place_id"].astype(str).isin([target_id, *leader_ids])]
        for record in frame.to_dict("records"):
            reads[str(record["google_place_id"])] = {"read_on": _date(record.get("completed_at") or record.get("started_at")),
                                                     "url": record.get("final_url") or record.get("requested_url")}
    usable = frame[frame["audit_status"].astype(str).isin(USABLE_AUDIT_STATUSES)] if not frame.empty else frame
    usable_leader_ids = [pid for pid in leader_ids if pid in set(usable["google_place_id"].astype(str))] if not usable.empty else []
    layer_note = ""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if not leader_ids:
            for key in ("website", "propositions", "reviews"):
                _unavailable(layers, key, "No business in the comparison set was recommended by the AI, so there are no leaders to compare with.")
        else:
            # ---- website and propositions
            if usable.empty or target_id not in set(usable["google_place_id"].astype(str)):
                _unavailable(layers, "website", "The client's website has no usable saved audit.")
                _unavailable(layers, "propositions", "The client's website has no usable saved audit.")
            elif not usable_leader_ids:
                _unavailable(layers, "website", "None of the most visible businesses has a saved website audit.")
                _unavailable(layers, "propositions", "None of the most visible businesses has a saved website audit.")
            else:
                try:
                    cohort_frame = usable[usable["google_place_id"].astype(str).isin([target_id, *usable_leader_ids])]
                    audit_profile = get_audit_profile(primary_group, extra_checks=to_audit_checks(type_wording))
                    ws = build_website_benchmark(target_google_place_id=target_id, audits=cohort_frame,
                                                 pages_by_run=dict(pages_by_run), profile=audit_profile)
                    if "error" in ws:
                        raise ValueError(ws["error"])
                    pages_by_place = {str(r["google_place_id"]): pages_by_run.get(str(r["id"]), pd.DataFrame()) for r in cohort_frame.to_dict("records")}
                    evals = {str(r["google_place_id"]): evaluate_business(r, pages_by_run.get(str(r["id"])), audit_profile) for r in cohort_frame.to_dict("records")}
                    layer_note = (f"Saved website pages of {target_name} and {len(usable_leader_ids)} of the {len(leader_ids)} most visible businesses "
                                  f"({_named([names[p] for p in usable_leader_ids])}), read between "
                                  f"{min(v['read_on'] for p, v in reads.items() if p in [target_id, *usable_leader_ids] and v['read_on'])} and "
                                  f"{max(v['read_on'] for p, v in reads.items() if p in [target_id, *usable_leader_ids] and v['read_on'])}")
                    layers["website"] = {"status": "used", "note": f"{len(usable_leader_ids)} of {len(leader_ids)} leaders had a saved website audit."}
                    if propositions:
                        cov = build_proposition_coverage(propositions=propositions, pages_by_place=pages_by_place, business_names=names)
                        pb = build_proposition_benchmark(coverage=cov, target_google_place_id=target_id)
                        layers["propositions"] = {"status": "used", "note": f"{len(propositions)} owner priorities checked against the saved pages."}
                    else:
                        _unavailable(layers, "propositions", "The owner gave no priorities to check.")
                    syn = build_recommendation_synthesis(
                        primary_group=primary_group, target_name=target_name, website_result=ws,
                        proposition_benchmark=pb if pb is not None else pd.DataFrame(), review_result=None, results=None, max_actions=12,
                    )
                    actions, te = syn["actions"], syn["technical_evidence"]
                    candidates += _website_candidates(
                        fb=ws["feature_benchmark"], te=te, evals=evals, names=names, reads=reads, target_id=target_id,
                        target_name=target_name, leader_ids=usable_leader_ids, profile=profile, layer_note=layer_note,
                        propositions=propositions)
                    if pb is not None and not pb.empty:
                        candidates += _proposition_candidates(actions=actions, pb=pb, cov=cov, names=names, reads=reads, target_id=target_id,
                                                              target_name=target_name, profile=profile, layer_note=layer_note)
                    strengths += [{"title": str(r["title"]), "evidence": str(r["evidence"]), "layer": "website"} for r in syn["strengths"].to_dict("records")]
                except Exception as exc:  # a failed layer never stops the report
                    _unavailable(layers, "website", f"The website comparison could not be completed ({type(exc).__name__}).")
                    layers.setdefault("propositions", {"status": "unavailable", "note": "The website comparison could not be completed."})
            # ---- reviews
            rev = reviews if reviews is not None else pd.DataFrame()
            target_reviews = int((rev["google_place_id"].astype(str) == target_id).sum()) if not rev.empty else 0
            leader_reviews = int(rev["google_place_id"].astype(str).isin(leader_ids).sum()) if not rev.empty else 0
            if target_reviews == 0 or leader_reviews == 0:
                _unavailable(layers, "reviews", "Review text is needed for the client and at least one of the most visible businesses"
                                                f" (saved: {target_reviews} for the client, {leader_reviews} for the leaders).")
            else:
                try:
                    rb = build_review_benchmark(target_google_place_id=target_id, reviews=rev[rev["google_place_id"].astype(str).isin([target_id, *leader_ids])],
                                                business_names=names, profile=_review_profile(primary_group, type_wording))
                    syn_r = build_recommendation_synthesis(primary_group=primary_group, target_name=target_name, website_result=None,
                                                           proposition_benchmark=pd.DataFrame(), review_result=rb, results=None, max_actions=12)
                    candidates += _review_findings(rb=rb, target_name=target_name, leader_ids=leader_ids, names=names, obs=syn_r["observations"])
                    layers["reviews"] = {"status": "used", "note": f"{target_reviews} client reviews and {leader_reviews} reviews of the leaders analysed."}
                except Exception as exc:
                    _unavailable(layers, "reviews", f"The review comparison could not be completed ({type(exc).__name__}).")
    candidates.sort(key=lambda c: (c["kind"] != "action", -float(c["score"]), c["id"]))
    return {
        "layers": layers,
        "leaders": [{"google_place_id": pid, "business_name": names[pid], "recommendations": int(next(i["recommendations"] for i in leaders if str(i["google_place_id"]) == pid)),
                     "website_read": reads.get(pid, {}).get("read_on"), "reviews": int((reviews["google_place_id"].astype(str) == pid).sum()) if reviews is not None and not reviews.empty else 0}
                    for pid in leader_ids],
        "candidates": candidates,
        "strengths": strengths,
        "basis": layer_note,
    }
