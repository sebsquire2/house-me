import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DEDUP_KEY = "seen_ids.json"


def _s3():
    return boto3.client("s3")


def load_seen(bucket: str) -> set[str]:
    try:
        obj = _s3().get_object(Bucket=bucket, Key=DEDUP_KEY)
        data = json.loads(obj["Body"].read())
        return set(data.get("ids", []))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return set()
        raise


def save_seen(bucket: str, seen: set[str]) -> None:
    _s3().put_object(
        Bucket=bucket,
        Key=DEDUP_KEY,
        Body=json.dumps({"ids": list(seen)}).encode(),
        ContentType="application/json",
    )


def filter_new(properties: list, seen: set[str]) -> list:
    return [p for p in properties if p.unique_id not in seen]
