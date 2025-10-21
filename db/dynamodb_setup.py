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

        response = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},  # Partition key
                {"AttributeName": "SK", "KeyType": "RANGE"}, # Sort key
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},  # status
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},  # tag
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",  # Filter by status
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI2",  # Filter by tag
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",  # serverless-friendly
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
