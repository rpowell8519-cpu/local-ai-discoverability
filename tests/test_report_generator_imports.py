"""Exercise page imports with a module retained from an older deployment."""
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("missing", [(), ("list_report_audit_revisions",), ("restore_report_audit_revision",),
                                    ("list_report_audit_revisions", "restore_report_audit_revision")])
def test_page_imports_recover_a_stale_report_repository(missing):
    # Isolate module reloads from Streamlit's process-wide module/cache tracking.
    script = '''
import ast
import importlib
from pathlib import Path
from unittest import mock
from src import report_audit_repository

page = Path("app/pages/10_AI_Report_Generator.py").resolve()
tree = ast.parse(page.read_text())
# Run the actual imports, stopping before UI/data access.
stop = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "BUILD_VERSION" for t in node.targets))
preamble = ast.Module(body=tree.body[:stop], type_ignores=[])
for name in MISSING:
    delattr(report_audit_repository, name)
namespace = {"__file__": str(page)}
with mock.patch("importlib.reload", wraps=importlib.reload) as reload:
    exec(compile(preamble, str(page), "exec"), namespace)
    if MISSING:
        reload.assert_called_once_with(report_audit_repository)
    else:
        reload.assert_not_called()
assert callable(namespace["list_report_audit_revisions"])
assert callable(namespace["restore_report_audit_revision"])
'''
    result = subprocess.run(
        [sys.executable, "-c", f"MISSING = {missing!r}\n" + script],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
