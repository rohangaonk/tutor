"""GET /documents/{user_id} — list documents for a user."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user
from common.db import get_db
from common.models import Document

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
) -> list[DocumentOut]:
    """Return all documents for the current user, newest first."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        DocumentOut(id=d.id, name=d.name, status=d.status.value, created_at=d.created_at)
        for d in docs
    ]
