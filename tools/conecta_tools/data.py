"""Table access for the tool Lambdas: local CSVs (DATA_DIR) or the same CSVs in S3 (DATA_BUCKET)."""

import csv
import io
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "out"


@lru_cache(maxsize=None)
def table(name: str) -> tuple[dict, ...]:
    bucket = os.environ.get("DATA_BUCKET")
    if bucket:
        import boto3

        key = f"{os.environ.get('DATA_PREFIX', 'raw')}/{name}/{name}.csv"
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        return tuple(csv.DictReader(io.StringIO(body)))
    with open(Path(os.environ.get("DATA_DIR", DEFAULT_DIR)) / f"{name}.csv", encoding="utf-8") as f:
        return tuple(csv.DictReader(f))


def one(name: str, **match) -> dict | None:
    return next((r for r in table(name) if all(r[k] == v for k, v in match.items())), None)


def where(name: str, **match) -> list[dict]:
    return [r for r in table(name) if all(r[k] == v for k, v in match.items())]


def customer(customer_id: str) -> dict:
    c = one("customers", customer_id=customer_id)
    if not c:
        raise ValueError(f"Unknown customer {customer_id}")
    return c
