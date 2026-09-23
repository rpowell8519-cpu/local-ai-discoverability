"""Execute each page's actual reload guard against a retained pre-fix provider."""
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('page', ['10_AI_Report_Generator.py', '8_AI_Visibility.py', '0_AI_Discovery_Scan.py'])
@pytest.mark.parametrize('stale', ['provider', 'runner', 'neither'])
def test_paid_run_refreshes_stale_provider(page, stale):
    script = '''
import ast
import importlib
from pathlib import Path
from unittest.mock import Mock, patch
import src.ai_visibility_runner as visibility_runner
import src.llm_providers.anthropic_provider as anthropic_provider
import src.llm_providers.base as provider_base
import src.llm_providers.openai_provider as openai_provider
import src.llm_providers.gemini_provider as gemini_provider
if STALE == 'provider':
    del anthropic_provider.REQUIRED_SEARCH_VERSION
    anthropic_provider.call_anthropic = Mock(side_effect=AssertionError('stale provider called'))
    visibility_runner.call_anthropic = anthropic_provider.call_anthropic
elif STALE == 'runner':
    visibility_runner.call_anthropic = Mock(side_effect=AssertionError('stale runner called'))
tree = ast.parse(Path('app/pages', PAGE).read_text())
guard = next(n for n in tree.body if isinstance(n, ast.If) and 'SUPPORTED_BENCHMARK_MODES' in ast.unparse(n.test))
with patch('importlib.reload', wraps=importlib.reload) as reload:
    exec(compile(ast.Module(body=[guard], type_ignores=[]), PAGE, 'exec'))
    assert reload.call_count == (0 if STALE == 'neither' else 5)
response = Mock(ok=True, status_code=200)
response.json.return_value = {'stop_reason':'end_turn', 'content':[
    {'type':'server_tool_use','name':'web_search'}, {'type':'text','text':'1. Nursery'}]}
with patch('src.llm_providers.anthropic_provider.requests.post', return_value=response) as post:
    result = visibility_runner._call_provider(provider='Claude', api_key='test', model='test',
        prompt='Nurseries?', benchmark_mode='search_grounded', location_context='Brighton')
assert result.response_complete
assert post.call_args.kwargs['json']['tool_choice'] == {'type':'tool','name':'web_search'}
'''
    result = subprocess.run([sys.executable, '-c', f'PAGE={page!r}\nSTALE={stale!r}\n'+script],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
