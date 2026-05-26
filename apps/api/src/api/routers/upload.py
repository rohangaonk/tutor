import json
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_current_user
from common.config import settings
from common.db import get_db
from common.models import Document, DocumentStatus

router = APIRouter(prefix="/upload", tags=["upload"])


def get_s3_client():
    endpoint_url = settings.aws_endpoint_url
    if endpoint_url is None and settings.s3_bucket.endswith("-local"):
        endpoint_url = "http://localhost:4566"

    kwargs: dict = {
        "region_name": settings.aws_region,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def get_sqs_client():
    endpoint_url = settings.aws_endpoint_url
    if endpoint_url is None and settings.sqs_queue_url.startswith("http://localhost"):
        endpoint_url = "http://localhost:4566"

    kwargs: dict = {
        "region_name": settings.aws_region,
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("sqs", **kwargs)


class PresignRequest(BaseModel):
    filename: str
    content_type: str


class PresignResponse(BaseModel):
    presigned_url: str
    s3_key: str


class ConfirmRequest(BaseModel):
    s3_key: str
    filename: str


class ConfirmResponse(BaseModel):
    document_id: uuid.UUID


@router.post("/presign", response_model=PresignResponse)
def presign_upload(
    body: PresignRequest,
    current_user: uuid.UUID = Depends(get_current_user),
) -> PresignResponse:
    s3 = get_s3_client()
    s3_key = f"{current_user}/{uuid.uuid4()}/{body.filename}"
    try:
        presigned_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": s3_key,
                "ContentType": body.content_type,
            },
            ExpiresIn=3600,
        )
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate upload URL.",
        ) from exc
    return PresignResponse(presigned_url=presigned_url, s3_key=s3_key)


@router.post("/confirm", response_model=ConfirmResponse, status_code=status.HTTP_201_CREATED)
def confirm_upload(
    body: ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
) -> ConfirmResponse:
    doc = Document(
        user_id=current_user,
        name=body.filename,
        s3_key=body.s3_key,
        status=DocumentStatus.pending,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    sqs = get_sqs_client()
    sqs.send_message(
        QueueUrl=settings.sqs_queue_url,
        MessageBody=json.dumps({"document_id": str(doc.id)}),
    )

    return ConfirmResponse(document_id=doc.id)
