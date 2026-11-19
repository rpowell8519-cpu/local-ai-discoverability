"""Chains: one business with several Google listings, counted once per answer (added 10 November 2026).

Most AI answers name a chain without saying which branch ("Topps Tiles", "Mastertiles"), so branch listings
split the count and the bare name was left unmatched. A reviewer-defined chain fixes that: every answer naming
any of its listings, or the chain itself in any of its written forms, counts once for the chain.

A chain is saved in the review decisions as
    {"name": "Topps Tiles", "place_ids": [...], "aliases": ["Topps"], "evidence_place_id": "..."}
and is credited to its evidence listing (the one whose website and reviews represent it), shown under the
chain's name. Everything downstream (step 5's leaders, the comparison set, recommendations, the report) then
treats the chain as one business without needing to know about chains. The branch an answer named is kept on
each row as `chain_branch_place_id`.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from src.owner_services_report import unmatched_key


class ChainError(ValueError):
    """A chain definition that cannot be applied safely."""


def clean_chains(chains: Iterable[Mapping[str, Any]] | None, *, target_id: str = "") -> list[dict[str, Any]]:
    """Validated chains: a name, at least one listing, an evidence listing among them, no listing in two chains."""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in chains or []:
        name = " ".join(str(raw.get("name") or "").split())
        place_ids = [str(item) for item in dict.fromkeys(raw.get("place_ids") or []) if str(item).strip()]
        if not name or not place_ids:
            raise ChainError("A chain needs a name and at least one Google listing.")
        if str(target_id) in place_ids:
            raise ChainError(f"The client cannot be part of the chain “{name}”.")
        clash = seen & set(place_ids)
        if clash:
            raise ChainError(f"A listing is in two chains: {', '.join(sorted(clash))}.")
        seen |= set(place_ids)
        evidence = str(raw.get("evidence_place_id") or place_ids[0])
        if evidence not in place_ids:
            raise ChainError(f"The evidence listing for “{name}” must be one of its listings.")
        aliases = [" ".join(str(item).split()) for item in raw.get("aliases") or [] if str(item).strip()]
        result.append({"name": name, "place_ids": place_ids, "aliases": aliases, "evidence_place_id": evidence})
    return result


def chain_names(chains: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """{evidence place ID: chain name}, for showing a chain under its own name."""

    return {str(chain["evidence_place_id"]): str(chain["name"]) for chain in chains}


def _lookups(chains: list[dict[str, Any]], places: frozenset[str]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_place = {pid: chain for chain in chains for pid in chain["place_ids"]}
    by_key: dict[str, dict] = {}
    for chain in chains:
        for written in [chain["name"], *chain["aliases"]]:
            key = unmatched_key(written, places)
            if key in by_key and by_key[key] is not chain:
                raise ChainError(f"“{written}” is a name of two chains.")
            by_key[key] = chain
    return by_place, by_key


def chain_for(place_id: Any, raw_name: Any, chains: list[dict[str, Any]], places: frozenset[str] = frozenset(),
              lookups: tuple[dict[str, dict], dict[str, dict]] | None = None) -> dict[str, Any] | None:
    """The chain a named business belongs to: by its matched listing, else (unmatched) by how the name is written."""

    if not chains:
        return None
    by_place, by_key = lookups or _lookups(chains, places)
    if place_id:
        return by_place.get(str(place_id))
    return by_key.get(unmatched_key(raw_name, places))


def apply_chains(records: pd.DataFrame, chains: list[dict[str, Any]], places: frozenset[str] = frozenset()) -> pd.DataFrame:
    """Credit each row naming a chain (by listing or by name) to the chain, once per answer.

    Rows matched to a listing outside every chain, and the client's own rows, are unchanged.
    """

    if records.empty or not chains:
        return records
    lookups = _lookups(chains, places)
    out = records.copy().astype({"google_place_id": object})
    branch: list[Any] = []
    for index, row in out.iterrows():
        place = row["google_place_id"] if pd.notna(row["google_place_id"]) else None
        chain = chain_for(place, row["raw_business_name"], chains, places, lookups)
        branch.append(place if chain else None)
        if chain:
            out.at[index, "google_place_id"] = chain["evidence_place_id"]
            out.at[index, "business_name"] = chain["name"]
            if not place:
                out.at[index, "resolution_status"] = "chain_name"
                if "classification" in out:
                    out.at[index, "classification"] = "AI-discovered"
    out["chain_branch_place_id"] = branch
    # An answer naming two branches (or a branch and the chain) still counts the chain once: keep its best place.
    answer = ["query_id", "provider"] if "query_id" in out else []
    if answer:
        chain_ids = {chain["evidence_place_id"] for chain in chains}
        is_chain = out["google_place_id"].isin(chain_ids)
        ordered = out.sort_values("position", kind="stable") if "position" in out else out
        dupes = ordered[is_chain.loc[ordered.index]].duplicated(subset=[*answer, "google_place_id"], keep="first")
        out = out.drop(index=dupes[dupes].index)
    return out
