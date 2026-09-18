#!/usr/bin/env bash
set -euo pipefail
ENDPOINT=${AWS_ENDPOINT_URL:-http://localhost:4566}
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo ">> Creating S3 bucket: onecall-raw-docs"
aws s3 mb s3://onecall-raw-docs --endpoint-url "$ENDPOINT" --region "$REGION" 2>/dev/null || true

echo ">> Creating FIFO queues"
for Q in onecall-classify.fifo onecall-extract.fifo onecall-prior-auth-agent.fifo onecall-denial-agent.fifo; do
  aws sqs create-queue --queue-name "$Q" \
    --attributes FifoQueue=true,ContentBasedDeduplication=true \
    --endpoint-url "$ENDPOINT" --region "$REGION" 2>/dev/null || true
done

echo ">> Creating standard queues"
for Q in onecall-triage-agent onecall-claim-processor onecall-eligibility-agent onecall-human-review onecall-dlq; do
  aws sqs create-queue --queue-name "$Q" --endpoint-url "$ENDPOINT" --region "$REGION" 2>/dev/null || true
done

echo ">> LocalStack resources ready"
