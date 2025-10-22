"""
Creates the DynamoDB single-table design for the Model Registry project.

Table: ArtifactsTable
Primary Key:
    PK = ART#<id>        (artifact ID)
    SK = META#<version>  (artifact version or related entity)

Attributes:
    - type, name, version, id, status, tags, trust_score
Global Secondary Indexes:
    - GSI1:  status index (for fast filtering by approval state)
    - GSI2:  tag index (for fast filtering/pagination by tags)

Usage:
    python db/dynamodb_setup.py
"""

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
TABLE_NAME = "ArtifactsTable"

dynamodb = boto3.client("dynamodb", region_name=REGION)


def create_table():
    try:
        print(f"Creating DynamoDB table '{TABLE_NAME}'...")

        # dynamodb_setup.py
        response = dynamodb.create_table(
            TableName="model_registry",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},  # MODEL#<id>
                {"AttributeName": "SK", "KeyType": "RANGE"}, # VER#<semver> or ARTIFACT#/NOTE#
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "tag", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status_index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "tags_index",
                    "KeySchema": [
                        {"AttributeName": "tag", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )


        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)

        print(f"Table '{TABLE_NAME}' created successfully in {REGION}.")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table '{TABLE_NAME}' already exists — skipping creation.")
        else:
            raise


if __name__ == "__main__":
    create_table()
