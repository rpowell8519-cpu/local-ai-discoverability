"""Versioned read-only projections of primary evidence, not AI-generated summaries."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any

from src.fact_consistency import compare_fact, normalize_fact
from src.proposition_catalog import label_key
from src.review_coverage import build_review_coverage
from src.review_ingestion import SOURCE
from src.review_profile_metrics import SOURCE_PLATFORMS
from src.site_checks import SAVED_TEXT_CAP, scan_contact_details

VERSION = "saved-evidence-matrix-v2"


def _date(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value else None


def observation(*, place_id, source_class, source_record_id, source_url, captured_at,
                raw_value, kind, field, normalized_value=None, source_published_at=None,
                identity_basis="stored_business_link", source_url_basis="stored_source_url") -> dict[str, Any]:
    if not place_id or not source_record_id:
        raise ValueError("Canonical identity and underlying record reference are required")
    row = {"google_place_id": str(place_id), "source_class": source_class,
           "source_record_id": str(source_record_id), "source_url": source_url,
           "source_url_basis": source_url_basis,
           "captured_at": _date(captured_at), "source_published_at": _date(source_published_at),
           "raw_value": raw_value, "normalized_value": normalized_value, "kind": kind,
           "field": field, "adapter_version": VERSION, "identity_basis": identity_basis,
           "identity_confidence": "not_reassessed", "freshness": "dated_capture" if captured_at else "capture_date_unknown"}
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    row["evidence_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
    row["evidence_id"] = f"{VERSION}:{row['evidence_sha256']}"
    return row


def proposition_mentions(text: str, catalogue, aliases) -> list[dict[str, Any]]:
    """Exact reviewed phrases in sentence context. Polarity hints never approve support."""
    terms = {}
    for item in [*aliases, *({"alias_text": c["label"], "proposition_key": c["proposition_key"]} for c in catalogue)]:
        terms.setdefault(item["proposition_key"], set()).add(label_key(item["alias_text"]))
    mentions = []
    # Keep the whole sentence for inspection; narrow hints to the matching clause.
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", text):
        sentence = match.group().strip()
        for key, values in terms.items():
            pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True)) + r")(?!\w)", re.I)
            if not pattern.search(label_key(sentence)):
                continue
            clauses = [c for c in re.split(r"\bbut\b|\bhowever\b|;", sentence, flags=re.I) if pattern.search(label_key(c))]
            hints = set()
            for clause in clauses:
                lower = label_key(clause)
                negative = bool(re.search(r"\b(?:not|never|no|poor|bad|awful|terrible|ruined|disappoint\w*|can't|cannot|couldn't|don't|doesn't|didn't)\b", lower))
                positive = bool(re.search(r"\b(?:excellent|great|amazing|lovely|love|loved|beautiful|brilliant|perfect|recommend|recommended)\b", lower))
                hints.add("mixed_or_negated" if negative and positive else "negative" if negative else "positive" if positive else "neutral")
            mentions.append({"proposition_key": key, "excerpt": sentence,
                             "polarity_hint": next(iter(hints)) if len(hints) == 1 else "mixed_or_negated",
                             "evidence_state": "REVIEW_REQUIRED", "extraction_basis": "exact_reviewed_phrase"})
    return mentions


def _mention_observations(*, place_id, source_class, record_id, text, source_url, captured_at, catalogue, aliases, published_at=None, source_url_basis="stored_source_url"):
    return [{**observation(place_id=place_id, source_class=source_class, source_record_id=record_id,
                          source_url=source_url, captured_at=captured_at, source_published_at=published_at,
                          raw_value=m["excerpt"], kind="proposition_candidate", field=m["proposition_key"], source_url_basis=source_url_basis), **m}
            for m in proposition_mentions(text, catalogue, aliases)]


def build_evidence_matrix(*, business, listing, audit, pages, reviews, platform_links,
                          checks, catalogue, aliases):
    """Read saved captures only; preserve the original sources and collection limitations."""
    pid = str(business["google_place_id"])
    observations, collection, facts = [], [], []
    raw = dict((listing or {}).get("raw_data") or {})
    listing_id = (listing or {}).get("id")
    listing_status = "COLLECTED" if listing_id else "NOT_CHECKED"
    collection.append({"source_class": "google_profile", "collection_status": listing_status,
                       "scope": "Saved Google listing capture", "captured_at": _date((listing or {}).get("created_at")),
                       "source_url": raw.get("location_link"), "sample_size": None})
    website_pages = [p for p in pages if p.get("http_status") == 200 and p.get("text_excerpt")]
    website_status = "COLLECTED" if website_pages else "FAILED" if audit and audit.get("audit_status") == "failed" else "UNAVAILABLE" if audit else "NOT_CHECKED"
    complete = bool(website_pages) and all(len(p["text_excerpt"]) < SAVED_TEXT_CAP for p in website_pages)
    collection.append({"source_class": "website", "collection_status": website_status,
                       "scope": "Saved readable pages only; not a complete website inventory",
                       "captured_at": _date((audit or {}).get("completed_at")), "source_url": (audit or {}).get("requested_url"),
                       "sample_size": len(website_pages), "complete_saved_text": complete})
    for field, raw_key in (("phone", "phone"), ("postcode", "postal_code")):
        reference = [raw[raw_key]] if raw.get(raw_key) else []
        observed = []
        field_ids = []
        if reference:
            o = observation(place_id=pid, source_class="google_profile", source_record_id=listing_id,
                            source_url=raw.get("location_link"), captured_at=listing.get("created_at"),
                            raw_value=reference[0], normalized_value=normalize_fact(field, reference[0]), kind="fact", field=field)
            observations.append(o)
            field_ids.append(o["evidence_id"])
        for p in website_pages:
            values = scan_contact_details(p["text_excerpt"])[0 if field == "phone" else 1]
            for normalized, written in values.items():
                o = observation(place_id=pid, source_class="website", source_record_id=p["id"],
                                source_url=p.get("final_url") or p.get("url"), captured_at=p.get("crawled_at"),
                                raw_value=written, normalized_value=normalized, kind="fact", field=field)
                observations.append(o)
                observed.append(written)
                field_ids.append(o["evidence_id"])
        # Repeat occurrences across pages do not create multiple facts.
        observed = list(dict.fromkeys(observed))
        comparison = compare_fact(field, reference, observed, collection_status=website_status, complete=complete)
        facts.append({"field": field, "Google profile": reference, "Website": observed,
                      **comparison, "comparison_scope": "Google capture versus saved readable website text; source-to-source only",
                      "evidence_ids": field_ids})
    for p in website_pages:
        observations.extend(_mention_observations(place_id=pid, source_class="website", record_id=p["id"],
            text=p["text_excerpt"], source_url=p.get("final_url") or p.get("url"), captured_at=p.get("crawled_at"), catalogue=catalogue, aliases=aliases))
    coverage_reviews = reviews.copy()
    if not coverage_reviews.empty and "source" not in coverage_reviews:
        coverage_reviews["source"] = SOURCE
    coverage = build_review_coverage(business_names={pid: business["business_name"]}, reviews=coverage_reviews,
                                    platform_links=platform_links, checks=checks)
    coverage_by_source = {r["source"]: r for r in coverage}
    for c in coverage:
        source_class = SOURCE_PLATFORMS[c["source"]] + "_reviews"
        collection.append({"source_class": source_class, "collection_status": "COLLECTED" if c["sampled_review_count"] else "CHECKED_EMPTY" if c["status"] == "checked" else "NOT_CHECKED",
                           "scope": c["note"], "captured_at": c["checked_at"], "source_url": c["source_url"],
                           "sample_size": c["found_count"], "profile_status": c["profile_status"]})
    seen = set()
    for r in coverage_reviews.to_dict("records"):
        source = r.get("source")
        key = (str(r.get("google_place_id")), source, str(r.get("review_id")))
        if key in seen or str(r.get("google_place_id")) != pid or not r.get("review_id"):
            continue
        seen.add(key)
        source_class = SOURCE_PLATFORMS.get(source, "unknown") + "_reviews"
        # Rating is deliberately never read: stars cannot determine proposition sentiment.
        observations.extend(_mention_observations(place_id=pid, source_class=source_class,
            record_id=r.get("id") or r["review_id"], text=str(r.get("review_text") or ""),
            source_url=r.get("review_link") or r.get("location_link") or coverage_by_source.get(source, {}).get("source_url"),
            source_url_basis="review_permalink" if r.get("review_link") else "collected_profile_url" if r.get("location_link") else "linked_profile_reference" if coverage_by_source.get(source, {}).get("source_url") else "unknown",
            captured_at=r.get("imported_at"), published_at=r.get("review_datetime_utc"), catalogue=catalogue, aliases=aliases))
    # Identical source/sentence observations are one item, not repeated support.
    observations = list({o["evidence_id"]: o for o in observations}.values())
    propositions = []
    source_classes = [c["source_class"] for c in collection]
    for prop in catalogue:
        candidates = [o for o in observations if o["kind"] == "proposition_candidate" and o["field"] == prop["proposition_key"]]
        if not candidates:
            continue
        cells = {}
        for source_class in source_classes:
            found = [o for o in candidates if o["source_class"] == source_class]
            cells[source_class] = f"REVIEW_REQUIRED · {len(found)} excerpts" if found else "UNKNOWN · no approved evidence"
        propositions.append({"proposition_key": prop["proposition_key"], "Proposition": prop["label"], **cells,
                             "candidate_source_classes": len({o["source_class"] for o in candidates}),
                             "substantive_evidence_breadth": None, "evidence_ids": [o["evidence_id"] for o in candidates]})
    return {"version": VERSION, "google_place_id": pid, "collection": collection, "facts": facts,
            "propositions": propositions, "observations": observations,
            "limitations": ["Phrase matches require operator review; candidate counts are not substantive corroboration.",
                            "Missing in saved pages is not absence from the entire website.",
                            "Google listing values are comparison observations, not approved canonical truth."]}
