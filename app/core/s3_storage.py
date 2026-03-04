"""
s3_storage.py — Upload project artifacts to S3.
"""
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_BUCKET", "blastshield-artifacts")


def upload_artifact(scan_id: str, content: bytes, bucket: str = None) -> dict:
    """
    Upload project artifact to S3.
    Key: scans/{scan_id}/project.zip
    Returns {"bucket": ..., "key": ...} on success, or None on failure.
    """
    bucket = bucket or S3_BUCKET
    key = f"scans/{scan_id}/project.zip"

    try:
        client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        client.put_object(Bucket=bucket, Key=key, Body=content)
        logger.info(f"✅ Uploaded artifact to s3://{bucket}/{key}")
        return {"bucket": bucket, "key": key}
    except ClientError as e:
        logger.warning(f"S3 upload failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"S3 upload error: {e}")
        return None
