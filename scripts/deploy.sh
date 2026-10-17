#!/usr/bin/env bash
# Full deploy to us-east-1: ECR first, then container images, then everything else in one apply.
set -euo pipefail
cd "$(dirname "$0")/.."
REGION=${AWS_REGION:-us-east-1}
TF="terraform -chdir=infra"

python3 data/generate.py
$TF init -input=false >/dev/null
# Only the registries: applying everything without image tags would remove the runtimes.
$TF apply -input=false -auto-approve -target=aws_ecr_repository.repo >/dev/null

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null

# Content-addressed tags (repos are immutable): a new tag only when the sources change.
tag() { (cd "$1" && find . -type f -not -path './target/*' -not -path '*/__pycache__/*' -print0 | sort -z | xargs -0 shasum | shasum | cut -c1-12); }
BILLING_TAG=$(tag mcp-billing-java)
AGENT_TAG=$(tag agent)

push() { # dir repo tag
  local uri="$REGISTRY/conecta/$2:$3"
  if ! aws ecr describe-images --region "$REGION" --repository-name "conecta/$2" --image-ids imageTag="$3" >/dev/null 2>&1; then
    docker buildx build --platform linux/arm64 -t "$uri" --push "$1"
  fi
}
push mcp-billing-java billing-mcp "$BILLING_TAG"
push agent care-agent "$AGENT_TAG"

$TF apply -input=false -auto-approve -var billing_image_tag="$BILLING_TAG" -var agent_image_tag="$AGENT_TAG"
$TF output
