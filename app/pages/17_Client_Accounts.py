"""Client accounts (beta): publish reviewed tests and reports to a client's signed-in area on the website.

Nothing here runs a paid test. The website shows only what is published from this page: a frozen copy of
each test's counts (src/client_account.py), never the live tables. Loading the page never writes; each
write is its own button.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

import src.client_account as account  # noqa: E402
import src.client_account_repository as repo  # noqa: E402

st.set_page_config(page_title="Client accounts", page_icon="🔐", layout="wide")
st.title("Client accounts (beta)")
st.caption("Publish a client's reviewed tests and reports to their signed-in area on foundinbrighton.ai. "
           "Clients see only what is published here, and only their own.")


def lines(value: str) -> list[str]:
    return [account.clean(line) for line in str(value or "").splitlines() if account.clean(line)]


try:
    ready = repo.stores_ready()
except Exception as exc:
    st.error(f"The database could not be reached ({type(exc).__name__}).")
    st.stop()
if not ready:
    st.warning("The client account tables are not in the database yet "
               "(`sql/20261016120000_client_accounts.sql`, awaiting approval). You can prepare and preview a test "
               "below and download it for the website preview; nothing can be published until the tables exist.")

operator = st.text_input("Your name (recorded with anything you publish)", key="acct_operator")

# --- Which client -------------------------------------------------------------------------------------------
clients = repo.list_client_accounts() if ready else []
if ready:
    with st.expander("Add a client account", expanded=not clients):
        slug = st.text_input("Short address name (lower case, e.g. wrap)")
        name = st.text_input("Client name as the client sees it (e.g. WRAP)")
        services_text = st.text_area("Services, one per line: name | Google Place ID | short name",
                                     placeholder="Coworking | ChIJO49ZdfyPdUgRx2HnXZqBjD0 | WRAP")
        if st.button("Create client account", disabled=not (slug and name and services_text and operator)):
            services = [dict(zip(("name", "place_id", "short_name"), [p.strip() for p in line.split("|")] + [""]))
                        for line in lines(services_text)]
            repo.create_client_account(slug.strip().lower(), name, services)
            st.success("Created.")
            st.rerun()
    if not clients:
        st.stop()
    client = st.selectbox("Client", clients, format_func=lambda c: c["name"])
    services = list(client["services"] or [])
else:
    client = {"id": None, "name": st.text_input("Client name (preview only)", value="WRAP"), "slug": "preview"}
    services = [dict(zip(("name", "place_id", "short_name"), [p.strip() for p in line.split("|")] + [""]))
                for line in lines(st.text_area("Services, one per line: name | Google Place ID | short name (preview only)",
                                               value="Coworking | ChIJO49ZdfyPdUgRx2HnXZqBjD0 | WRAP\n"
                                                     "Nursery | ChIJp-aHNLOFdUgREf2CB7XC9r0 |"))]
if not services:
    st.info("This client has no services yet.")
    st.stop()

publish_tab, tests_tab, reports_tab, people_tab = st.tabs(["Publish a test", "Published tests", "Reports", "Who has access"])

# --- Publish a test -----------------------------------------------------------------------------------------
def publish_section() -> None:
    service = st.selectbox("Service", services, format_func=lambda s: s["name"])
    runs = repo.load_runs(service["place_id"])
    if not runs:
        st.info("No completed tests for this service.")
        return
    chosen = st.multiselect(
        "Test runs (pick every run from the one test day)", runs, default=runs[:1],
        format_func=lambda r: f'{r["created_at"]:%d %b %Y %H:%M} · {r["prompts"]} prompts · {r["answers"]} answers · {r["run_id"][:8]}')
    if not chosen:
        return
    days = {r["created_at"].date() for r in chosen}
    left_out = [r for r in runs if r["created_at"].date() in days and r not in chosen]
    if left_out:
        st.warning("Another completed run from the same day is not selected, so its prompts would be missing: "
                   + "; ".join(f'{r["created_at"]:%H:%M} · {r["prompts"]} prompts · {r["run_id"][:8]}' for r in left_out)
                   + ". Add it unless it was a repeat you do not want.")
    tested_on = st.date_input("Test date the client sees", value=min(r["created_at"] for r in chosen).date())
    previous = repo.latest_decisions(client["id"], service["name"]) if ready else None
    start = account.carry_forward(previous, client_names=[] if previous else repo.load_reviewed_names(service["place_id"]),
                                  short_name=service.get("short_name") or "")
    st.caption("Starting from the decisions saved with this service's last published test." if previous else
               "Starting from the names confirmed in this business's latest reviewed report.")

    key = f'{service["place_id"]}:{",".join(sorted(r["run_id"] for r in chosen))}'
    rows = repo.load_answers([r["run_id"] for r in chosen])
    left, right = st.columns(2)
    with left:
        client_names = lines(st.text_area("Names that are the client (one per line)", "\n".join(start["client_names"]), key=f"names:{key}"))
        short_name = st.text_input("Short name, matched only in exactly this letter case (blank for none)", start["short_name"],
                                   key=f"short:{key}")
    with right:
        rejected = lines(st.text_area("Look-alike names that are another business (one per line)",
                                      "\n".join(start["rejected_names"]), key=f"rejected:{key}"))
        own_domains = lines(st.text_area("The client's own websites (one per line)", "\n".join(start["own_domains"]), key=f"own:{key}"))
    decisions = {**start, "client_names": client_names, "short_name": short_name, "rejected_names": rejected,
                 "own_domains": own_domains}

    undecided = account.undecided_client_names(rows, decisions)
    if undecided:
        st.subheader("Decide these names")
        st.caption("These recommended names look like the client and are on neither list. Each must be decided before publishing.")
        for item in undecided:
            choice = st.radio(f'"{item["name"]}" ({item["answers"]} answers)', ["Not decided", "It is the client", "Another business"],
                              horizontal=True, key=f'decide:{key}:{item["name"]}')
            if choice == "It is the client":
                decisions["client_names"].append(item["name"])
            elif choice == "Another business":
                decisions["rejected_names"].append(item["name"])
        undecided = account.undecided_client_names(rows, decisions)

    st.subheader("Prompt sets")
    st.caption("The client's graph shows a set's total only on tests that asked every prompt in it. Rewording a prompt starts a new line.")
    prompt_texts = list(dict.fromkeys(account.clean(r["prompt_text"]) for r in sorted(rows, key=lambda r: (r["run_order"], r["base_prompt_order"]))))
    known_sets = sorted(set(start["prompt_sets"].values()), key=str.casefold)
    added = lines(st.text_area("New sets, one per line (they then appear in the Set list)", key=f"newsets:{key}", height=80))
    sets = st.data_editor(
        pd.DataFrame({"Prompt": prompt_texts, "Set": [start["prompt_sets"].get(t) for t in prompt_texts],
                      "Note for the client": [start["prompt_notes"].get(t, "") for t in prompt_texts]}),
        column_config={"Set": st.column_config.SelectboxColumn(
            "Set", options=list(dict.fromkeys([*known_sets, *added])), required=True),
            "Note for the client": st.column_config.TextColumn(
                "Note for the client", max_chars=300,
                help="Optional. Shown with this prompt's figures, e.g. why a count should be read with care.")},
        disabled=["Prompt"], hide_index=True, width='stretch', key=f"sets:{key}")
    decisions["prompt_sets"] = {**start["prompt_sets"], **{r["Prompt"]: account.clean(r["Set"]) for _, r in sets.iterrows() if isinstance(r["Set"], str) and account.clean(r["Set"])}}
    decisions["prompt_notes"] = {**{t: n for t, n in start["prompt_notes"].items() if t not in prompt_texts},
                                 **{r["Prompt"]: account.clean(r["Note for the client"]) for _, r in sets.iterrows()
                                    if isinstance(r["Note for the client"], str) and account.clean(r["Note for the client"])}}
    unset = [t for t in prompt_texts if t not in decisions["prompt_sets"]]

    st.subheader("Competitor spellings")
    st.caption("Group the spellings and branches of one business so it is counted once per answer. "
               "One line per business: the name the client sees, a colon, then the spellings separated by semicolons.")
    groups_text = st.text_area("Groups", "\n".join(f'{label}: {"; ".join(names)}' for label, names in start["competitor_groups"].items()),
                               key=f"groups:{key}", height=120)
    decisions["competitor_groups"] = {account.clean(label): [account.clean(n) for n in names.split(";") if account.clean(n)]
                                      for label, _, names in (line.partition(":") for line in lines(groups_text)) if account.clean(label)}
    with st.expander("Every other business the answers recommended, after grouping"):
        st.dataframe(pd.DataFrame([{"Business": c["name"], "Answers": c["answers"], "Spellings": "; ".join(c["spellings"])}
                                   for c in account.competitor_names(rows, decisions)]), hide_index=True, width='stretch')

    st.subheader("Preview")
    if undecided or unset:
        st.info("Decide every name above and give every prompt a set to see the figures.")
        return
    models = {r["provider"]: r["model"] for r in rows if r.get("model")}
    payload = account.project_test(rows, decisions, tested_on=tested_on.isoformat(), models=models)
    st.dataframe(pd.DataFrame([{
        "Set": p["set"], "Prompt": p["text"], "Recommended": f'{p["recommended"]} of {p["answers"]}',
        **{tool: f'{v["recommended"]} of {v["answers"]}' for tool, v in p["providers"].items()},
        "Top competitor": (p["competitors"][0]["name"] + f' ({p["competitors"][0]["answers"]})') if p["competitors"] else "",
        "Own site cited": p["own_site_answers"],
    } for p in payload["prompts"]]), hide_index=True, width='stretch')
    note = st.text_area("Note to the client shown with this test (optional)", key=f"note:{key}", max_chars=1200)

    preview = {"client": {"name": client["name"], "slug": client.get("slug"), "services": [s["name"] for s in services]},
               "tests": [{"service": service["name"], "tested_on": payload["tested_on"], "payload": payload, "note": note or None}]}
    st.download_button("Download this preview for the website (JSON)", json.dumps(preview, indent=1, default=str),
                       file_name=f'{client.get("slug") or "client"}-{service["name"].lower()}-{payload["tested_on"]}.json',
                       mime="application/json")
    checked = st.checkbox("I have checked these figures against the answers and they can be shown to the client", key=f"checked:{key}")
    if st.button("Publish to the client's account", type="primary", disabled=not (ready and checked and operator)):
        repo.publish_test(client["id"], service["name"], service["place_id"], [r["run_id"] for r in chosen], payload,
                          decisions, note, operator)
        st.success(f'Published {service["name"]}, {tested_on:%d %B %Y}. A test already published for that day was withdrawn.')

with publish_tab:
    publish_section()

if not ready:
    for tab in (tests_tab, reports_tab, people_tab):
        with tab:
            st.info("Available once the client account tables exist.")
    st.stop()

# --- Published tests ----------------------------------------------------------------------------------------
with tests_tab:
    next_note = st.text_input("Next test, as the client sees it (e.g. Early November)", client.get("next_test_note") or "")
    if st.button("Save next test note"):
        repo.set_next_test_note(client["id"], next_note)
        st.rerun()
    for test in repo.list_tests(client["id"]):
        prompts = test["payload"]["prompts"]
        label = (f'{test["service"]} · {test["tested_on"]:%d %b %Y} · {sum(p["recommended"] for p in prompts)} of '
                 f'{sum(p["answers"] for p in prompts)} · published {test["published_at"]:%d %b} by {test["published_by"]}')
        if test["withdrawn_at"]:
            st.caption(f"~~{label}~~ withdrawn {test['withdrawn_at']:%d %b}")
            continue
        left, right = st.columns([5, 1])
        left.write(label)
        if right.button("Withdraw", key=f'withdraw:{test["id"]}'):
            repo.withdraw("client_account_tests", test["id"])
            st.rerun()

# --- Reports ------------------------------------------------------------------------------------------------
with reports_tab:
    upload = st.file_uploader("Report PDF", type=["pdf"])
    service_name = st.selectbox("Service", [s["name"] for s in services], key="report_service")
    title = st.text_input("Title the client sees", "AI visibility findings")
    report_date = st.date_input("Report date", value=date.today(), key="report_date")
    if st.button("Publish report", disabled=not (upload and title and operator)):
        file_name = re.sub(r"[^A-Za-z0-9._ -]", "", upload.name)[:116] or "report"
        file_name = file_name if file_name.lower().endswith(".pdf") else file_name + ".pdf"
        repo.publish_report(client["id"], service_name, title, report_date.isoformat(), file_name, upload.getvalue(), operator)
        st.rerun()
    for report in repo.list_reports(client["id"]):
        left, right = st.columns([5, 1])
        left.write(f'{"~~" if report["withdrawn_at"] else ""}{report["service"]} · {report["title"]} · {report["report_date"]:%d %b %Y} · '
                   f'{report["size"] / 1e6:.1f} MB{"~~ withdrawn" if report["withdrawn_at"] else ""}')
        if not report["withdrawn_at"] and right.button("Withdraw", key=f'withdraw-report:{report["id"]}'):
            repo.withdraw("client_account_reports", report["id"])
            st.rerun()

# --- Who has access -----------------------------------------------------------------------------------------
with people_tab:
    st.caption("A person signs in on foundinbrighton.ai/account with a password set up for them in Supabase, or an emailed link. They see this client only while listed here.")
    for member in repo.list_members(client["id"]):
        left, right = st.columns([5, 1])
        left.write(f'{member["display_name"] or ""} · {member["email"]} · added {member["added_at"]:%d %b %Y} by {member["added_by"]}')
        if right.button("Remove", key=f'remove:{member["id"]}'):
            repo.remove_member(member["id"])
            st.rerun()
    email = st.text_input("Email address")
    display = st.text_input("Name")
    if st.button("Give access", disabled=not (email and "@" in email and operator)):
        repo.add_member(client["id"], email, display, operator)
        st.rerun()
