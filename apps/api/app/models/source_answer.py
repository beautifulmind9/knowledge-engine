"""Experimental source answers; no KnowledgeAsset or saved-output schema changes."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceAnswerRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=2000)
    question_scope: Literal['targeted','broad','visual']
    source_ids: list[str] = Field(default_factory=list,max_length=20)
    library_id: str | None = Field(default=None,max_length=200)
    max_passages: int = Field(default=24,ge=1,le=24)
    max_words: int = Field(default=6000,ge=1,le=6000)
    max_chars: int = Field(default=48000,ge=1,le=48000)

    @model_validator(mode='after')
    def explicit_scope(self):
        if not self.source_ids and not self.library_id:
            raise ValueError('Select sources or a library explicitly.')
        return self


class SourceCitation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_ref: str = Field(min_length=1,max_length=100)
    start_char: int = Field(ge=0,strict=True)
    end_char: int = Field(ge=1,strict=True)
    quote: str = Field(min_length=1,max_length=16000)


class SourceAnswerSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['source_supported','interpretation','uncertainty']
    heading: str = Field(min_length=1,max_length=180)
    content: str = Field(min_length=1,max_length=12000)
    citations: list[SourceCitation] = Field(max_length=10)

    @model_validator(mode='after')
    def cited_claim(self):
        if self.kind=='source_supported' and not self.citations:
            raise ValueError('Source-supported sections require citations.')
        return self


class SourceAnswerDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    disposition: Literal['answered','insufficient_evidence','broader_coverage_required','unsupported_content']
    title: str = Field(min_length=1,max_length=500)
    sections: list[SourceAnswerSection] = Field(max_length=12)
    limitations: list[str] = Field(max_length=12)

    @model_validator(mode='after')
    def cited_answer(self):
        if self.disposition=='answered' and not any(s.kind=='source_supported' for s in self.sections):
            raise ValueError('An answered response requires cited source-supported content.')
        return self
