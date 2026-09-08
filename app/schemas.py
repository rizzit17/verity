from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentBase(BaseModel):
    filename: str


class DocumentCreate(DocumentBase):
    pass


class DocumentRead(DocumentBase):
    id: str
    uploaded_at: datetime
    page_count: int
    status: str
    error_message: Optional[str] = None
    fact_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class FactBase(BaseModel):
    page: int
    printed_page_label: Optional[str] = None
    subject: str
    metric: str
    value: str
    unit: Optional[str] = None
    time_scope: Optional[str] = None
    fact_type: Optional[str] = "other"
    evidence_text: str
    evidence_context: Optional[str] = None
    confidence: float = 1.0
    attributes: Dict[str, Any] = Field(default_factory=dict)


class FactCreate(FactBase):
    document_id: str


class FactRead(FactBase):
    id: str
    document_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RelationshipBase(BaseModel):
    fact_a_id: str
    fact_b_id: str
    relation_type: str  # corroborates, contradicts, contextual_reconciliation, unrelated
    reasoning: str
    confidence: float = 1.0
    reconciliation_note: Optional[str] = None


class RelationshipCreate(RelationshipBase):
    pass


class RelationshipRead(RelationshipBase):
    id: str
    created_at: datetime
    fact_a: Optional[FactRead] = None
    fact_b: Optional[FactRead] = None

    model_config = ConfigDict(from_attributes=True)


class ExtractionFailureRead(BaseModel):
    id: str
    document_id: str
    page: Optional[int] = None
    raw_item: Dict[str, Any] = Field(default_factory=dict)
    reason: str
    status: str = "pending"
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_fact_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentProcessSummary(BaseModel):
    document_id: str
    filename: str
    page_count: int
    facts_extracted: int
    relationships_found: int
    failures_count: int
    status: str
