"""No network calls on import or report render. Implement collection in your backend."""
from typing import Callable, Protocol
from .schema import Observation, Prompt, Provider

class VisibilityCollector(Protocol):
    provider: Provider
    def collect(self, prompt: Prompt) -> Observation:
        """Return a normalized, reviewed observation including preserved answer text."""
        ...

class ProviderHook:
    def __init__(self, provider: Provider, collect_fn: Callable[[Prompt], Observation] | None = None):
        self.provider = provider
        self.collect_fn = collect_fn

    def collect(self, prompt: Prompt) -> Observation:
        if self.collect_fn is None:
            raise NotImplementedError(
                f'{self.provider} collection is not configured. Supply collect_fn(prompt). '
                'Preserve the response, annotate mentions/citations/facts, and return Observation.'
            )
        result = Observation.model_validate(self.collect_fn(prompt))
        if result.provider != self.provider or result.prompt_id != prompt.id:
            raise ValueError('Collector returned a mismatched provider or prompt')
        return result

class OpenAIHook(ProviderHook):
    def __init__(self, collect_fn=None):
        super().__init__('OpenAI', collect_fn)

class ClaudeHook(ProviderHook):
    def __init__(self, collect_fn=None):
        super().__init__('Claude', collect_fn)

class GeminiHook(ProviderHook):
    def __init__(self, collect_fn=None):
        super().__init__('Gemini', collect_fn)
