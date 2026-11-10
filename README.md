# Local AI Discoverability

Internal tool for auditing AI discoverability of local businesses: the Streamlit operator console, the
reports it produces, and the worker behind the website's free visibility check.

Read `AGENTS.md` first. It holds the working rules (database safety, paid calls, Git workflow) and how each
part works.

## Run

Settings come from an ignored `.env` (at least `DATABASE_URL`) or `.streamlit/secrets.toml`. The
configured database may be production: keep local use read-only unless agreed.

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/streamlit_app.py
env PYTHONPATH=. .venv/bin/pytest -q
```

The free-check worker makes paid calls; see `src/free_check_worker.py` before running it.

## Layout

- `app/`: Streamlit pages (`app/shelved_pages/` are hidden from the app).
- `src/`: domain logic, reports and the free-check worker.
- `sql/`: migrations. Never apply one without explicit approval.
- `tests/`: pytest suite and a few Node tests for SQL.
- `docs/`: process notes and dated build records.
- `render.yaml`: free-check worker deployment.
