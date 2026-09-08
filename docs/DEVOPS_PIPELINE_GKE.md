# JobsRSS DevOps Pipeline (GitHub Actions + GKE)

This is the GCP deployment path. It replaces Azure VM + Docker Compose for
runtime, while keeping the same images (`jobsrss-api`, `jobsrss-frontend`).

Flow:

1. CI still runs on every PR/push (`.github/workflows/ci.yml`).
2. CD builds images and pushes them to Artifact Registry.
3. CD applies Kubernetes manifests to GKE (`api`, `worker`, `frontend`, `postgres`).

Do not run `docker-compose.prod.yml` on GKE. Compose stays for local/Azure VM.

## 1) Repository files

- `.github/workflows/deploy-gke.yml`
- `deploy/gke/*.yaml` (workloads + GCE Ingress)
- `deploy/gke/.env.gke.example`
- `deploy/gke/scripts/bootstrap-gcp.sh`
- `deploy/gke/scripts/apply-secrets.sh`
- `deploy/gke/scripts/apply-workloads.sh`
- `deploy/jenkins/Jenkinsfile.gke`

## 2) One-time GCP bootstrap

Need `gcloud` and `kubectl` locally, with Owner or equivalent on the project.

```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=asia-southeast1
export GKE_CLUSTER=jobsrss
export AR_REPOSITORY=jobsrss

gcloud auth login
gcloud config set project "$GCP_PROJECT_ID"
bash deploy/gke/scripts/bootstrap-gcp.sh
```

The script enables APIs, creates:

- Artifact Registry Docker repo
- GKE Autopilot cluster
- CI/CD service account `jobsrss-cicd` with
  `roles/artifactregistry.writer` and `roles/container.developer`
- namespace `jobsrss`

Create a key for GitHub (or Jenkins):

```bash
gcloud iam service-accounts keys create cicd-sa.json \
  --iam-account="jobsrss-cicd@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
```

Keep `cicd-sa.json` off git.

Autopilot already NATs node egress. Official collectors (Microsoft, BCG, etc.)
can reach the public internet. LinkedIn/Liepin from GKE IPs are still usually
blocked; leave those collectors disabled unless you front the worker with a
residential VPN.

## 3) App secrets (once per cluster, not in CI)

```bash
cp deploy/gke/.env.gke.example /tmp/jobsrss.env.gke
# set POSTGRES_PASSWORD, DATABASE_URL (same password), ALLOWED_ORIGINS, RSS_BASE_URL
bash deploy/gke/scripts/apply-secrets.sh /tmp/jobsrss.env.gke /path/to/secrets
```

`/path/to/secrets` is optional. If present it may contain:

- `linkedin_state.json`
- `liepin_state.json`

Those files are mounted at `/secrets` (read-only), matching the Compose layout.
CI never overwrites `jobsrss-env`; missing that secret fails the deploy on
purpose.

After Ingress gets an IP, update `ALLOWED_ORIGINS` and `RSS_BASE_URL` in the
env file, re-run `apply-secrets.sh`, then:

```bash
kubectl -n jobsrss rollout restart deploy/api deploy/frontend
```

## 4) GitHub configuration

Repository **variables**:

- `GCP_PROJECT_ID`
- `GCP_REGION` (example: `asia-southeast1`)
- `GKE_CLUSTER` (example: `jobsrss`)
- `AR_REPOSITORY` (optional, default `jobsrss`)
- `GKE_DEPLOY_ENABLED` = `true` only when you want push-to-`main` to deploy

Repository **secret**:

- `GCP_SA_KEY` — full JSON key for `jobsrss-cicd`

Manual deploy always works from Actions: **Deploy to GKE**.
Auto-deploy on `main` stays off until `GKE_DEPLOY_ENABLED=true`.

If you fully leave Azure VM, disable `.github/workflows/deploy-azure-vm.yml`
or stop using those Azure secrets.

## 5) CD behavior

Workflow: `.github/workflows/deploy-gke.yml`

1. Build/push
   `${REGION}-docker.pkg.dev/${PROJECT}/${AR_REPOSITORY}/jobsrss-api:${GIT_SHA}`
   and `jobsrss-frontend`.
2. `gcloud`/`kubectl` auth to the Autopilot cluster.
3. `bash deploy/gke/scripts/apply-workloads.sh`
4. Wait for postgres/api/frontend/worker rollouts.

Mapping from Compose:

| Compose service | GKE object | Notes |
|---|---|---|
| `postgres` | StatefulSet + PVC `standard-rwo` 10Gi | In-cluster; Cloud SQL is a later hardening step |
| `api` | Deployment + Service `:8000` | `/healthz` readiness |
| `worker` | Deployment, 1 replica, Recreate | Playwright `/dev/shm`; do not HPA this |
| `frontend` | Deployment + Service `:80` → 3000 | `BACKEND_API_BASE_URLS=http://api:8000` |
| `./secrets` | Secret `jobsrss-collector-files` | Optional |

Ingress (GCE) routes:

- `/` → frontend
- `/healthz`, `/jobs`, `/rss`, `/sources` → api

```bash
kubectl -n jobsrss get ingress jobsrss
```

Portal: `http://<INGRESS_IP>/`
API health: `http://<INGRESS_IP>/healthz`

## 6) First deployment checklist

1. Merge this branch to `main` (or run the workflow with `deploy_ref` set).
2. Run `bootstrap-gcp.sh`.
3. Apply `.env.gke` secrets.
4. Set GitHub variables + `GCP_SA_KEY`.
5. Run **Deploy to GKE** once.
6. Patch `ALLOWED_ORIGINS` / `RSS_BASE_URL` with the Ingress IP or domain.
7. Optional: attach a static IP + Google-managed certificate later.

## 7) Jenkins alternative

`deploy/jenkins/Jenkinsfile.gke` uses the same scripts.

Jenkins credentials:

- `gcp-sa-key` (file)
- `gcp-project-id`, `gcp-region`, `gke-cluster`

## 8) Cloud SQL (optional later)

The in-cluster Postgres is the Compose-equivalent default. To move to Cloud SQL:

1. Create Cloud SQL Postgres 16.
2. Run Cloud SQL Auth Proxy as a sidecar or use the built-in connector.
3. Point `DATABASE_URL` at the proxy/private IP.
4. Remove the `postgres` StatefulSet.

Do not store database credentials in git; keep using `jobsrss-env`.
