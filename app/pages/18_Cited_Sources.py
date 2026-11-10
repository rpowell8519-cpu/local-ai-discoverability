"""Which websites the AI tools cite, by business type, area, AI tool and over time. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.citation_sources import (CATALOG_PATH, CLIENT_SITE, SOURCE_TYPES, UNCLASSIFIED, build_records,
                                  by_business_type, load_source_types, over_time, rank_websites, sample, type_mix)
from src.citation_sources_repository import load_cited_results
from src.final_beta_repository import load_business_domains

FEW_BUSINESSES = 3

st.set_page_config(page_title="Cited sources", page_icon="📚", layout="wide")
st.title("Cited sources")
st.caption("The websites the AI tools cite when answering our test questions. A website counts once per answer "
           "that cites it. Only answers saved with their citations are included (tests from about 6 October 2026 "
           "onward). Read-only; refreshes every ten minutes.")


@st.cache_data(ttl=600)
def load():
    return build_records(load_cited_results(), business_domains=load_business_domains(), catalog=load_source_types())


try:
    all_answers, all_citations = load()
except Exception as exc:
    st.error(f"Citation data could not be loaded ({type(exc).__name__}).")
    st.stop()
if all_answers.empty:
    st.info("No answers with saved citations yet.")
    st.stop()


def options(column):
    return sorted(all_answers[column].dropna().unique())


with st.sidebar:
    st.header("Selection")
    kinds = st.multiselect("Kind of test", options("test_kind"), default=options("test_kind"))
    types = st.multiselect("Business type", options("business_type"), placeholder="All business types")
    areas = st.multiselect("Area", options("area"), placeholder="All areas")
    tools = st.multiselect("AI tool", options("ai_tool"), placeholder="All AI tools")
    first, last = all_answers["answered_on"].min(), all_answers["answered_on"].max()
    dates = st.date_input("Answered between", (first, last), min_value=first, max_value=last, format="DD/MM/YYYY")
    leave_out_own = st.checkbox("Leave out each business's own website", value=False,
                                help="Show only websites other than the tested business's own.")

keep = all_answers["test_kind"].isin(kinds)
for column, chosen in (("business_type", types), ("area", areas), ("ai_tool", tools)):
    if chosen:
        keep &= all_answers[column].isin(chosen)
if isinstance(dates, tuple) and len(dates) == 2:
    keep &= all_answers["answered_on"].between(*dates)
answers = all_answers[keep]
citations = all_citations[all_citations["answer_id"].isin(set(answers["answer_id"]))]
if leave_out_own:
    citations = citations[citations["source_type"] != CLIENT_SITE]

base = sample(answers)
if not base["answers_with_citations"]:
    st.info("No answers in this selection cited a website.")
    st.stop()


def describe(base):
    return (f"{base['businesses']} business{'es' if base['businesses'] != 1 else ''}, {base['tests']} test"
            f"{'s' if base['tests'] != 1 else ''}, {base['answers_with_citations']:,} answers citing a website, "
            f"{base['first'].day} {base['first']:%b} to {base['last'].day} {base['last']:%b %Y}")


a, b, c, d = st.columns(4)
a.metric("Businesses tested", base["businesses"])
b.metric("Tests", base["tests"])
c.metric("Answers citing a website", f"{base['answers_with_citations']:,}",
         f"of {base['answers']:,} answers", delta_color="off")
d.metric("Websites cited", f"{citations['website'].nunique():,}")
if base["businesses"] < FEW_BUSINESSES:
    st.caption(f"This selection rests on {', '.join(base['business_names'])} only, so it describes "
               f"{'that business' if base['businesses'] == 1 else 'those businesses'} rather than the business type.")

WEBSITE_COLUMNS = {
    "website": "Website", "source_type": "Kind of website", "belongs_to": "Belongs to",
    "answers": st.column_config.NumberColumn("Answers citing it", help="Each website counts once per answer."),
    "share_of_answers": st.column_config.ProgressColumn(
        "Share of answers", format="percent", min_value=0, max_value=1,
        help="Of the answers in this selection that cited any website."),
    "share_each_business_equal": st.column_config.ProgressColumn(
        "Share, each business equal", format="percent", min_value=0, max_value=1,
        help="The average of each tested business's own share, so a business tested often weighs no more "
             "than one tested once."),
    "businesses": st.column_config.NumberColumn("Businesses", help="Tested businesses whose answers cited it."),
    "questions": "Questions", "ai_tools": "AI tools",
    "first_seen": st.column_config.DateColumn("First seen", format="D MMM YYYY"),
    "last_seen": st.column_config.DateColumn("Last seen", format="D MMM YYYY"),
    "example_page": st.column_config.LinkColumn("Example page"),
}

ranked_tab, kinds_tab, types_tab, time_tab, unclassified_tab = st.tabs(
    ["Most cited websites", "Kinds of website", "By business type", "Over time", "Not yet classified"])

with ranked_tab:
    order = st.radio("Rank by", ["Answers citing it", "Share, each business equal"], horizontal=True,
                     help="Ranking by answers favours the businesses we tested most. Giving each business equal "
                          "weight shows what is common across businesses.")
    shown_types = st.multiselect("Kinds of website", [kind for kind in SOURCE_TYPES if kind in set(citations["source_type"])],
                                 placeholder="All kinds")
    ranked = rank_websites(answers, citations)
    if shown_types:
        ranked = ranked[ranked["source_type"].isin(shown_types)]
    if order != "Answers citing it":
        ranked = ranked.sort_values(["share_each_business_equal", "answers"], ascending=False)
    st.dataframe(ranked, hide_index=True, width="stretch", column_config=WEBSITE_COLUMNS)

with kinds_tab:
    st.caption("How many answers cited at least one website of each kind. An answer can cite several kinds, "
               "so the shares add up to more than 100%.")
    mix = type_mix(answers, citations).sort_values("answers", ascending=False)
    st.bar_chart(mix.set_index("source_type")["share_of_answers"].rename("Share of answers"), horizontal=True)
    st.dataframe(mix, hide_index=True, width="stretch", column_config={
        "source_type": "Kind of website", "answers": "Answers citing one",
        "share_of_answers": st.column_config.ProgressColumn("Share of answers", format="percent", min_value=0,
                                                            max_value=1),
        "websites": "Different websites"})

with types_tab:
    st.caption("The most cited websites for each business type in the selection, best-evidenced types first.")
    top = st.slider("Websites per business type", 5, 25, 10)
    for segment in by_business_type(answers, citations, top=top):
        seg = segment["sample"]
        if not seg["answers_with_citations"]:
            continue
        st.subheader(segment["business_type"])
        st.caption(describe(seg) + (f". Rests on {', '.join(seg['business_names'])} only."
                                    if seg["businesses"] < FEW_BUSINESSES else ""))
        st.dataframe(segment["websites"], hide_index=True, width="stretch",
                     column_config={**WEBSITE_COLUMNS, "first_seen": None, "last_seen": None, "questions": None})

with time_tab:
    st.caption("For one website: the share of each test's citing answers that cited it, per business.")
    sites = rank_websites(answers, citations)["website"].tolist()
    if sites:
        website = st.selectbox("Website", sites)
        trend = over_time(answers, citations, website)
        if trend["tested_on"].nunique() > 1:
            st.line_chart(trend.pivot_table(index="tested_on", columns="business", values="share", aggfunc="mean"))
        else:
            st.caption("Only one test date in this selection, so there is no trend to draw yet.")
        st.dataframe(trend, hide_index=True, width="stretch", column_config={
            "business": "Business", "tested_on": st.column_config.DateColumn("Tested on", format="D MMM YYYY"),
            "answers_with_citations": "Answers citing any website", "answers_citing": "Answers citing this one",
            "share": st.column_config.ProgressColumn("Share", format="percent", min_value=0, max_value=1)})

with unclassified_tab:
    unknown = rank_websites(answers, citations[citations["source_type"] == UNCLASSIFIED])
    st.caption(f"Websites not yet in the reviewed list (`src/{CATALOG_PATH.name}`) and not recognised as a business's "
               "own site. Add a line `domain,kind` to the list for each one checked; nothing is guessed.")
    if unknown.empty:
        st.success("Every cited website in this selection is classified.")
    else:
        st.dataframe(unknown.drop(columns=["source_type", "belongs_to", "share_each_business_equal"]),
                     hide_index=True, width="stretch", column_config=WEBSITE_COLUMNS)

st.divider()
st.download_button("Download the selected citations (CSV)", citations.to_csv(index=False).encode("utf-8"),
                   file_name="cited-sources.csv", mime="text/csv")
not_linked = sorted(all_answers.loc[all_answers["business"].str.endswith("(listing not confirmed)"), "business"].unique())
if not_linked:
    st.caption("Not yet matched to a Google listing, so counted under the name they were tested as: "
               + ", ".join(not_linked) + ". Link one in `src/citation_listing_matches.csv` once its listing is checked.")
