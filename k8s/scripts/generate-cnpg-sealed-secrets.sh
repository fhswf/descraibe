#!/usr/bin/env bash
set -euo pipefail

# Generate random CNPG bootstrap credentials and print SealedSecret ciphertexts.
# Usage:
#   ./k8s/scripts/generate-cnpg-sealed-secrets.sh release
#   ./k8s/scripts/generate-cnpg-sealed-secrets.sh staging
#
# Prereqs: kubeseal configured against the target cluster's controller.
# Defaults:
#   controller name: sealed-secrets
#   controller namespace: kube-system
# Override with:
#   SEALED_SECRETS_CONTROLLER_NAME=...
#   SEALED_SECRETS_CONTROLLER_NAMESPACE=...

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <release|staging>" >&2
  exit 1
fi

env="$1"
case "$env" in
  release)
    namespace="audiodeskription"
    app_secret_name="descraibe-db-app-user"
    super_secret_name="descraibe-db-superuser"
    ;;
  staging)
    namespace="audiodeskription-staging"
    app_secret_name="descraibe-db-app-user-staging"
    super_secret_name="descraibe-db-superuser-staging"
    ;;
  *)
    echo "unknown env: $env (expected release|staging)" >&2
    exit 1
    ;;
esac

app_user="descraibe_app"
super_user="postgres"
app_password="$(openssl rand -base64 36 | tr -d '\n')"
super_password="$(openssl rand -base64 36 | tr -d '\n')"
controller_name="${SEALED_SECRETS_CONTROLLER_NAME:-sealed-secrets}"
controller_namespace="${SEALED_SECRETS_CONTROLLER_NAMESPACE:-kube-system}"

seal_raw() {
  local value="$1"
  local name="$2"
  printf '%s' "$value" | kubeseal --raw --scope strict --namespace "$namespace" --name "$name" \
    --controller-name "$controller_name" \
    --controller-namespace "$controller_namespace"
}

echo "# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) for $env"
echo "app.username: $(seal_raw "$app_user" "$app_secret_name")"
echo "app.password: $(seal_raw "$app_password" "$app_secret_name")"
echo "super.username: $(seal_raw "$super_user" "$super_secret_name")"
echo "super.password: $(seal_raw "$super_password" "$super_secret_name")"
