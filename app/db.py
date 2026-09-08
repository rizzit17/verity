import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    page_count = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, done, failed
    error_message = Column(Text, nullable=True)

    # Relationships
    facts = relationship("FactModel", back_populates="document", cascade="all, delete-orphan")
    failures = relationship("ExtractionFailureModel", back_populates="document", cascade="all, delete-orphan")


class FactModel(Base):
    __tablename__ = "facts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False)
    printed_page_label = Column(String(50), nullable=True)
    subject = Column(String(255), nullable=False, index=True)
    metric = Column(String(255), nullable=False, index=True)
    value = Column(String(255), nullable=False)
    unit = Column(String(100), nullable=True)
    time_scope = Column(String(150), nullable=True)
    fact_type = Column(String(100), default="other", nullable=True)
    evidence_text = Column(Text, nullable=False)
    evidence_context = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0, nullable=False)
    attributes_json = Column(Text, default="{}", nullable=False)
    embedding = Column(LargeBinary, nullable=True)  # numpy float32 bytes
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    document = relationship("DocumentModel", back_populates="facts")

    @property
    def attributes(self) -> Dict[str, Any]:
        if not self.attributes_json:
            return {}
        try:
            return json.loads(self.attributes_json)
        except Exception:
            return {}

    @attributes.setter
    def attributes(self, val: Dict[str, Any]):
        self.attributes_json = json.dumps(val or {})

    def set_embedding(self, vec: np.ndarray):
        if vec is not None:
            self.embedding = np.ascontiguousarray(vec, dtype=np.float32).tobytes()
        else:
            self.embedding = None

    def get_embedding(self) -> Optional[np.ndarray]:
        if self.embedding:
            return np.frombuffer(self.embedding, dtype=np.float32)
        return None


class RelationshipModel(Base):
    __tablename__ = "relationships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    fact_a_id = Column(String(36), ForeignKey("facts.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_b_id = Column(String(36), ForeignKey("facts.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)  # corroborates, contradicts, contextual_reconciliation, unrelated
    reasoning = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    reconciliation_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Fact references
    fact_a = relationship("FactModel", foreign_keys=[fact_a_id])
    fact_b = relationship("FactModel", foreign_keys=[fact_b_id])


class ExtractionFailureModel(Base):
    __tablename__ = "extraction_failures"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=True)
    raw_item_json = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(32), default="pending", nullable=False)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_fact_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("DocumentModel", back_populates="failures")


def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            # Check if content_hash column exists in documents table
            result = conn.execute(text("PRAGMA table_info(documents);")).fetchall()
            col_names = [r[1] for r in result]
            if "content_hash" not in col_names:
                conn.execute(text("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64);"))
                conn.commit()

            # Check if status and resolution columns exist in extraction_failures table
            fail_result = conn.execute(text("PRAGMA table_info(extraction_failures);")).fetchall()
            fail_cols = [r[1] for r in fail_result]
            if "status" not in fail_cols:
                conn.execute(text("ALTER TABLE extraction_failures ADD COLUMN status VARCHAR(32) DEFAULT 'pending';"))
            if "resolution_notes" not in fail_cols:
                conn.execute(text("ALTER TABLE extraction_failures ADD COLUMN resolution_notes TEXT;"))
            if "resolved_at" not in fail_cols:
                conn.execute(text("ALTER TABLE extraction_failures ADD COLUMN resolved_at DATETIME;"))
            if "resolved_fact_id" not in fail_cols:
                conn.execute(text("ALTER TABLE extraction_failures ADD COLUMN resolved_fact_id VARCHAR(36);"))
            conn.commit()

            # Sweep any documents left stuck in processing or pending from interrupted past sessions
            conn.execute(text("UPDATE documents SET status = 'failed', error_message = 'Extraction interrupted or terminated unexpectedly' WHERE status IN ('processing', 'pending');"))
            conn.commit()
    except Exception as e:
        pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
