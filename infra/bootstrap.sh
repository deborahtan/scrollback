#!/usr/bin/env bash
# Scrollback one-time Google Cloud setup. Run in Cloud Shell (shell.cloud.google.com):
#
#   git clone https://github.com/deborahtan/scrollback && cd scrollback
#   bash infra/bootstrap.sh <PROJECT_ID>
#
# Safe to re-run: every step checks before it creates.
# What it does:
#   - enables the APIs Scrollback uses
#   - creates the archive bucket (versioned) and the BigQuery dataset + tables
#   - creates two service accounts: scrollback-run (runtime) and scrollback-deploy (CI)
#   - lets GitHub Actions in deborahtan/scrollback deploy WITHOUT any key file
#     (Workload Identity Federation)
#   - prints the values to paste into the GitHub repo settings
set -euo pipefail

PROJECT="${1:?Usage: bash infra/bootstrap.sh <PROJECT_ID>}"
REGION="${REGION:-australia-southeast1}"   # Sydney; switch to the Auckland region if your console offers it
DATASET="${DATASET:-scrollback}"
BUCKET="${BUCKET:-${PROJECT}-scrollback-archive}"
GITHUB_REPO="${GITHUB_REPO:-deborahtan/scrollback}"

gcloud config set project "$PROJECT" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
echo "Project $PROJECT ($PROJECT_NUMBER), region $REGION"

echo "1/6 Enabling APIs (takes a minute)..."
gcloud services enable \
  bigquery.googleapis.com aiplatform.googleapis.com run.googleapis.com \
  cloudscheduler.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com drive.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

echo "2/6 Archive bucket (versioned, private)..."
if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
# Versioning keeps every version of preferences.yaml, which is how Undo works.
gcloud storage buckets update "gs://$BUCKET" --versioning

echo "3/6 BigQuery dataset and tables..."
bq --location="$REGION" show "$PROJECT:$DATASET" >/dev/null 2>&1 \
  || bq --location="$REGION" mk --dataset "$PROJECT:$DATASET"
sed "s/\${dataset}/$PROJECT.$DATASET/g" sql/schema.sql \
  | bq query --use_legacy_sql=false --location="$REGION" >/dev/null

echo "4/6 Service accounts..."
for SA in scrollback-run scrollback-deploy; do
  gcloud iam service-accounts describe "$SA@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "$SA" --display-name="$SA"
done
RUN_SA="scrollback-run@$PROJECT.iam.gserviceaccount.com"
DEPLOY_SA="scrollback-deploy@$PROJECT.iam.gserviceaccount.com"

bind() { gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$1" \
           --role="$2" --condition=None >/dev/null; }
# Runtime: read/write its own data, call Gemini, read secrets. Nothing else.
bind "$RUN_SA" roles/bigquery.dataEditor
bind "$RUN_SA" roles/bigquery.jobUser
bind "$RUN_SA" roles/aiplatform.user
bind "$RUN_SA" roles/secretmanager.secretAccessor
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$RUN_SA" --role=roles/storage.objectAdmin >/dev/null
# Deploy: build and deploy Cloud Run, act as the runtime account.
bind "$DEPLOY_SA" roles/run.admin
bind "$DEPLOY_SA" roles/artifactregistry.admin
bind "$DEPLOY_SA" roles/cloudbuild.builds.editor
bind "$DEPLOY_SA" roles/storage.admin
bind "$DEPLOY_SA" roles/cloudscheduler.admin
bind "$DEPLOY_SA" roles/bigquery.dataEditor
bind "$DEPLOY_SA" roles/bigquery.jobUser
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --member="serviceAccount:$DEPLOY_SA" --role=roles/iam.serviceAccountUser >/dev/null

echo "5/6 Keyless deploys from GitHub ($GITHUB_REPO)..."
POOL=github
gcloud iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers describe "$POOL" --location=global \
  --workload-identity-pool="$POOL" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "$POOL" --location=global \
       --workload-identity-pool="$POOL" --issuer-uri="https://token.actions.githubusercontent.com" \
       --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
       --attribute-condition="assertion.repository=='$GITHUB_REPO'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$GITHUB_REPO" \
  >/dev/null

echo "6/6 Secret placeholder for Pinterest..."
gcloud secrets describe pinterest-refresh-token >/dev/null 2>&1 \
  || gcloud secrets create pinterest-refresh-token --replication-policy=automatic

cat <<EOF

Done. Two things left for you:

A) Share your Google Drive folder "Scrollback inspo" with this address as Viewer:
     $RUN_SA

B) In GitHub -> $GITHUB_REPO -> Settings -> Secrets and variables -> Actions -> Variables,
   add these repository variables:
     GCP_PROJECT        = $PROJECT
     GCP_REGION         = $REGION
     GCP_WIF_PROVIDER   = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$POOL
     GCP_DEPLOY_SA      = $DEPLOY_SA
     SCROLLBACK_BUCKET  = $BUCKET
EOF
