"""Validated interchange format; generate JSON Schema with Report.model_json_schema()."""
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Provider = Literal['OpenAI', 'Claude', 'Gemini']

class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Brand(Record):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)

    @field_validator('domains')
    @classmethod
    def domains_only(cls, values):
        if any(not d or '/' in d or ':' in d or ' ' in d for d in values):
            raise ValueError('Use hostnames only, such as example.com')
        return [d.lower().removeprefix('www.') for d in values]

class Prompt(Record):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    intent: Literal['discovery', 'comparison', 'transactional', 'branded'] = 'discovery'
    location: str | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    effort: int | None = Field(default=None, ge=1, le=5)

class Mention(Record):
    brand_id: str
    recommended: bool = False
    position: int | None = Field(default=None, ge=1)
    recommendation_position: int | None = Field(default=None, ge=1)
    sentiment: Literal['positive', 'neutral', 'negative', 'mixed', 'unknown'] = 'unknown'

    @model_validator(mode='after')
    def valid_rank(self):
        if self.recommendation_position is not None and not self.recommended:
            raise ValueError('A recommendation rank requires recommended=True')
        return self

class Citation(Record):
    url: str
    title: str = ''
    source_type: Literal['owned', 'directory', 'review', 'editorial', 'social', 'other'] = 'other'

    @field_validator('url')
    @classmethod
    def safe_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Citation URL must be an absolute HTTP(S) URL without credentials')
        return value

class FactCheck(Record):
    brand_id: str
    field: str = Field(min_length=1)
    expected: str
    observed: str
    verdict: Literal['correct', 'incorrect', 'unverifiable']
    evidence: str = Field(min_length=1, description='Source of truth and review rationale')

class Observation(Record):
    id: str = Field(min_length=1)
    prompt_id: str
    provider: Provider
    model: str = Field(min_length=1)
    surface: Literal['api', 'consumer', 'manual']
    configuration: str = Field(min_length=1, description='Stable ID for search, locale, sampling and session settings')
    collected_at: datetime
    status: Literal['ok', 'error', 'refused'] = 'ok'
    error: str | None = None
    answer: str = ''
    mentions: list[Mention] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    citation_status: Literal['measured', 'unavailable'] = 'measured'
    fact_checks: list[FactCheck] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid_observation(self):
        if self.collected_at.tzinfo is None:
            raise ValueError('collected_at must include a timezone')
        if self.status != 'ok' and (self.mentions or self.citations or self.fact_checks):
            raise ValueError('Non-successful observations cannot contain scored evidence')
        if self.status == 'ok' and not self.answer:
            raise ValueError('Successful observations require the preserved answer')
        ids = [m.brand_id for m in self.mentions]
        if len(ids) != len(set(ids)):
            raise ValueError('Record each brand at most once per answer')
        for attr in ('position', 'recommendation_position'):
            ranks = [getattr(m, attr) for m in self.mentions if getattr(m, attr) is not None]
            if len(ranks) != len(set(ranks)):
                raise ValueError('Assigned ranks must be unique within an answer')
        return self

class RoadmapItem(Record):
    horizon: Literal[30, 60, 90]
    action: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    success_measure: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    status: Literal['planned', 'in progress', 'complete'] = 'planned'

class Report(Record):
    schema_version: Literal['1.0'] = '1.0'
    client_id: str
    agency: str
    category: str
    market: str
    start_date: date
    end_date: date
    sample_data: bool = False
    executive_summary: str = ''
    methodology_notes: str = ''
    brands: list[Brand] = Field(min_length=1)
    prompts: list[Prompt] = Field(min_length=1)
    observations: list[Observation] = Field(default_factory=list)
    roadmap: list[RoadmapItem] = Field(default_factory=list)

    @model_validator(mode='after')
    def references(self):
        if self.end_date < self.start_date:
            raise ValueError('end_date must not precede start_date')
        for name in ('brands', 'prompts', 'observations'):
            ids = [r.id for r in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f'Duplicate {name} IDs')
        brands = {b.id for b in self.brands}
        prompts = {p.id for p in self.prompts}
        if self.client_id not in brands:
            raise ValueError('client_id must reference brands')
        for obs in self.observations:
            if obs.prompt_id not in prompts:
                raise ValueError(f'Unknown prompt {obs.prompt_id}')
            if not self.start_date <= obs.collected_at.date() <= self.end_date:
                raise ValueError('Observation date must fall within the reporting period')
            if any(m.brand_id not in brands for m in obs.mentions + obs.fact_checks):
                raise ValueError('Observation references an unknown brand')
        return self
