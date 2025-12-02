#!/bin/bash
# Script to view CloudWatch logs for the Lambda function

# Set your AWS region (modify if needed)
REGION="us-east-2"

# You need to replace this with your actual Lambda function name
# You can find it in AWS Console > Lambda > Functions
FUNCTION_NAME="model-registry-api"

echo "Fetching CloudWatch logs for $FUNCTION_NAME in $REGION..."
echo "========================================================"
echo ""

# Tail the logs in real-time
aws logs tail /aws/lambda/$FUNCTION_NAME \
  --follow \
  --format short \
  --region $REGION \
  --since 5m

# Alternative: Get last 100 lines
# aws logs tail /aws/lambda/$FUNCTION_NAME \
#   --format short \
#   --region $REGION \
#   --since 10m
