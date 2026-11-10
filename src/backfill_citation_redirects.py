"""One-off: record where saved Google citation redirects point, while they still work.

Answers saved before the runner resolved redirects hold only Google's redirect link and the website's name as the
link title (sometimes just "uk.com"). This adds ``resolved_url`` beside each redirect that still answers; nothing
else in the saved answer changes, and a citation that has changed since it was read is skipped.

    python -m src.backfill_citation_redirects            # counts only, writes nothing
    python -m src.backfill_citation_redirects --apply    # writes resolved_url
"""
from __future__ import annotations

import argparse
import copy
import json

from sqlalchemy import text

from src.citation_sources import _is_redirect, redirect_location, resolve_redirects
from src.database import get_engine

SELECT_SQL = """
    select id, report_metadata->'citations' as citations
    from public.ai_visibility_results
    where report_metadata->>'citation_status' = 'measured'
      and report_metadata->'citations' @? '$[*] ? (@.url like_regex "vertexaisearch" && !exists(@.resolved_url))'
    order by created_at desc
"""
UPDATE_SQL = """
    update public.ai_visibility_results
    set report_metadata = jsonb_set(report_metadata, '{citations}', cast(:new as jsonb))
    where id = :id and report_metadata->'citations' = cast(:old as jsonb)
"""


def main(apply: bool) -> None:
    engine = get_engine()
    with engine.connect() as connection:
        rows = connection.execute(text(SELECT_SQL)).all()
    answers = links = resolved = written = 0
    for result_id, citations in rows:
        updated = copy.deepcopy(citations)
        todo = sum(1 for cite in updated if _is_redirect(str(cite.get("url") or "")) and not cite.get("resolved_url"))
        found = resolve_redirects(updated, redirect_location, max_links=len(updated))
        answers, links, resolved = answers + 1, links + todo, resolved + found
        if apply and found:
            with engine.begin() as connection:
                written += connection.execute(text(UPDATE_SQL), {
                    "id": result_id, "old": json.dumps(citations), "new": json.dumps(updated)}).rowcount
    print(f"{answers} answers, {links} unresolved redirect links, {resolved} still resolve.")
    print(f"Wrote {written} answers." if apply else "Dry run: nothing written. Re-run with --apply to save.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="save resolved_url (default: count only)")
    main(parser.parse_args().apply)
