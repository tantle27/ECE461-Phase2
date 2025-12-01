"""
Seeds the DynamoDB ArtifactsTable with EXAMPLE data for testing and development.

Each item follows the single-table design:
    PK  = ART#<id>
    SK  = META#<version>
    GSI1 = status index (STATUS#<status>)
    GSI2 = tag index (TAG#<tag>)

Notes:
- All items include is_example=True and a name prefix "[EXAMPLE]".
- IDs are prefixed with "EX-" to avoid collisions with real data.

Usage:
    python db/seed_data.py
"""

from datetime import datetime, timezone
from decimal import Decimal

import boto3

REGION = "us-east-1"
TABLE_NAME = "ArtifactsTable"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)  # type: ignore[attr-defined]


def seed_data():
    artifacts = [
        {
            "id": "EX-1001",
            "name": "[EXAMPLE] audience-classifier",
            "type": "model",
            "version": "v1.0.0",
            "status": "approved",
            "tags": ["example", "transformer", "nlp"],
            "total_score": 0.95,
        },
        {
            "id": "EX-1002",
            "name": "[EXAMPLE] image-segmenter",
            "type": "model",
            "version": "v2.1.0",
            "status": "unvetted",
            "tags": ["example", "vision", "segmentation"],
            "total_score": 0.68,
        },
        {
            "id": "EX-1003",
            "name": "[EXAMPLE] sentiment-dataset",
            "type": "dataset",
            "version": "v3.0.0",
            "status": "approved",
            "tags": ["example", "nlp", "text"],
            "total_score": 0.88,
        },
        {
            "id": "EX-1004",
            "name": "[EXAMPLE] regression-benchmark",
            "type": "dataset",
            "version": "v1.2.0",
            "status": "archived",
            "tags": ["example", "benchmark", "tabular"],
            "total_score": 0.74,
        },
    ]

    print(f"Seeding {len(artifacts)} EXAMPLE items into '{TABLE_NAME}'...")

    for art in artifacts:
        item = {
            "PK": f"ART#{art['id']}",
            "SK": f"META#{art['version']}",
            "id": art["id"],
            "name": art["name"],
            "type": art["type"],
            "version": art["version"],
            "status": art["status"],
            "tags": art["tags"],
            "is_example": True,
            # DynamoDB does not support float; use Decimal for numbers
            "total_score": Decimal(str(art["total_score"])),
            # Use timezone-aware UTC timestamp to avoid deprecation warnings
            "created_at": datetime.now(timezone.utc).isoformat(),
            # GSI1 = status index
            "GSI1PK": f"STATUS#{art['status']}",
            "GSI1SK": f"ART#{art['id']}#VER#{art['version']}",
            # GSI2 = tag index (one per tag)
        }

        # For each tag, we can insert a duplicate item in GSI2 if needed.
        # To keep it simple, we’ll store just the first tag.
        if art["tags"]:
            first_tag = art["tags"][0]
            item["GSI2PK"] = f"TAG#{first_tag}"
            item["GSI2SK"] = f"ART#{art['id']}#VER#{art['version']}"

        table.put_item(Item=item)
        print(f"  Inserted: {art['name']} ({art['status']})")

    print("Seeding data complete!")


if __name__ == "__main__":
    seed_data()
