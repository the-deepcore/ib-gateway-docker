"""
S3 storage adapter.

Centralises all S3 interactions: calibration JSON files,
HTML report uploads, and presigned URL generation.
"""

import os
import json
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

BUCKET = "thedeepcore"
CALIBRATION_PREFIX = "calibrations/"

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")

_client = None


def _get_client():
    global _client
    if _client is None:
        session = boto3.Session(
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION,
        )
        _client = session.client("s3")
    return _client


def upload_json(data: Dict[str, Any], key: str) -> None:
    """Upload a Python dict as JSON to S3 under calibrations/."""
    _get_client().put_object(
        Bucket=BUCKET,
        Key=CALIBRATION_PREFIX + key,
        Body=json.dumps(data, indent=2),
        ContentType="application/json",
    )


def download_json(key: str) -> Dict[str, Any]:
    """Download a JSON from S3 calibrations/ and return as dict."""
    resp = _get_client().get_object(
        Bucket=BUCKET,
        Key=CALIBRATION_PREFIX + key,
    )
    return json.loads(resp["Body"].read())


def upload_file(local_path: str, s3_key: str) -> None:
    """Upload a local file to S3 bucket root."""
    _get_client().upload_file(local_path, BUCKET, s3_key)
    print(f"File {local_path} uploaded to bucket {BUCKET} as {s3_key}.")


def generate_presigned_url(key: str, expires_in: int = 86400 * 5) -> str:
    """Generate a presigned GET URL for an S3 object."""
    try:
        url = _get_client().generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError:
        print(f"Couldn't get a presigned URL for key '{key}'.")
        raise
    return url


def bulk_upload_calibrations(file_paths: list) -> None:
    """Upload a list of local JSON files to S3 under calibrations/."""
    from pathlib import Path

    for path in file_paths:
        p = Path(path)
        with open(p, "r") as f:
            data = json.load(f)
        upload_json(data, p.name)
        print(f"Uploaded {p.name} -> s3://{BUCKET}/{CALIBRATION_PREFIX}{p.name}")
