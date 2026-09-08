# JobsRSS DevOps Pipeline (Cloud Shell + GKE)

This is the GCP deployment path. It replaces Azure VM + Docker Compose for
runtime, while keeping the same images (`jobsrss-api`, `jobsrss-frontend`).

**Cloud Shell is the supported operator console.** It already has `gcloud`,
`kubectl`, and `git`. Do not install GitHub Actions on GKE or in Cloud Shell.

Preferred flow:

1. Bootstrap the cluster from Cloud Shell.
2. Apply app secrets from Cloud Shell.
3. Build images with **Cloud Build** and apply manifests
   (`deploy/gke/scripts/cloud-shell-deploy.sh`).

Do not run `docker-compose.prod.yml` on GKE. Do not `docker build` the backend
image inside Cloud Shell — Playwright will fill the Cloud Shell disk.

## GitHub Actions: do not install it

GitHub Actions is a service on github.com, not a package for GKE/Cloud Shell.

- You do **not** install an Actions runner on the cluster.
- You do **not** install Actions in Cloud Shell.
- Cloud Shell + Cloud Build is enough to ship this app.
- GitHub Actions is optional later: only configure repo secrets/variables in
  the GitHub UI if you want push-to-`main` deploys. No GCP-side install.

## 1) Repository files

- `deploy/gke/*.yaml` (workloads + HTTPRoute on an existing GKE Gateway)
- `deploy/gke/cloudbuild.yaml`
- `deploy/gke/.env.gke.example`
- `deploy/gke/scripts/bootstrap-gcp.sh`
- `deploy/gke/scripts/apply-secrets.sh`
- `deploy/gke/scripts/apply-workloads.sh`
- `deploy/gke/scripts/cloud-shell-deploy.sh`
- `.github/workflows/deploy-gke.yml` (optional, GitHub-hosted)
- `deploy/jenkins/Jenkinsfile.gke`

## 2) Cloud Shell bootstrap

In the GCP console: **Activate Cloud Shell**. Cloud Shell starts in `~`,
so clone the repo and `cd` into it first. These scripts are on branch
`cursor/jobs-intelligence-bootstrap-0a74` (not `main` yet):

```bash
cd ~
git clone -b cursor/jobs-intelligence-bootstrap-0a74 \
  https://github.com/Vincentssssssss/JobsRSS.git
cd JobsRSS

export GCP_PROJECT_ID=your-project-id
export GCP_REGION=asia-southeast1
export AR_REPOSITORY=jobsrss

gcloud config set project "$GCP_PROJECT_ID"
gcloud container clusters list
export GKE_CLUSTER=your-existing-cluster-name

ls deploy/gke/scripts/bootstrap-gcp.sh
bash deploy/gke/scripts/bootstrap-gcp.sh
```

Cloud Shell is already logged in as your user. Skip `gcloud auth login` unless
the project is on another account.

The script **does not create a GKE cluster or VPC**. It attaches to the cluster
you already have. If `GKE_CLUSTER` is omitted and the project has exactly one
cluster, that cluster is used.

It may still create (if missing):

- Artifact Registry Docker repo `jobsrss` (images only)
- Cloud Build write access to that repo
- namespace `jobsrss` inside the existing cluster

Skip creating a JSON key unless you later enable GitHub Actions.

Autopilot already NATs node egress. Official collectors (Microsoft, BCG, etc.)
can reach the public internet. LinkedIn/Liepin from GKE IPs are still usually
blocked; leave those collectors disabled unless you front the worker with a
residential VPN.

## 3) App secrets (once per cluster, from Cloud Shell)

```bash
cp deploy/gke/.env.gke.example /tmp/jobsrss.env.gke
# paste LLM_API_KEY; RSS_BASE_URL / ALLOWED_ORIGINS default to jobsrss.vincentspace.com
bash deploy/gke/scripts/apply-secrets.sh /tmp/jobsrss.env.gke /path/to/secrets
```

`/path/to/secrets` is optional. If present it may contain:

- `linkedin_state.json`
- `liepin_state.json`

Those files are mounted at `/secrets` (read-only), matching the Compose layout.
CI never overwrites `jobsrss-env`; missing that secret fails the deploy on
purpose.

After the Gateway gets an IP, update `ALLOWED_ORIGINS` and `RSS_BASE_URL` in the
env file, re-run `apply-secrets.sh`, then:

```bash
kubectl -n jobsrss rollout restart deploy/api deploy/frontend
```

## 4) Deploy from Cloud Shell

After secrets exist:

```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=asia-southeast1
export GKE_CLUSTER=your-existing-cluster-name
bash deploy/gke/scripts/cloud-shell-deploy.sh
```

This submits `deploy/gke/cloudbuild.yaml` (backend + frontend in parallel),
then `kubectl apply` to the existing cluster. Backend image build can take
15–30 minutes because of Playwright.

Enterprise projects often disable the default Compute service account
(`…-compute@developer.gserviceaccount.com`). The deploy script creates and
uses `jobsrss-cicd@…` instead — do not enable the default Compute SA.

Check the load balancer:

```bash
kubectl -n jobsrss get gateway jobsrss
kubectl -n jobsrss get pods
```

Portal: `http://<GATEWAY_IP>/`  
API health: `http://<GATEWAY_IP>/healthz`

## 5) Optional GitHub Actions (hosted by GitHub, not installed here)

Only if you want github.com to deploy on push. No runner install on GKE.

Repository **variables**:

- `GCP_PROJECT_ID`
- `GCP_REGION` (example: `asia-southeast1`)
- `GKE_CLUSTER` (existing cluster name)
- `GKE_LOCATION` (cluster region or zone, if different from `GCP_REGION`)
- `AR_REPOSITORY` (optional, default `jobsrss`)
- `GKE_DEPLOY_ENABLED` = `true` only when you want push-to-`main` to deploy

Repository **secret**:

- `GCP_SA_KEY` — full JSON key for `jobsrss-cicd`

Manual deploy always works from Actions: **Deploy to GKE**.
Auto-deploy on `main` stays off until `GKE_DEPLOY_ENABLED=true`.

If you fully leave Azure VM, disable `.github/workflows/deploy-azure-vm.yml`
or stop using those Azure secrets.

## 6) What gets deployed

Cloud Build / optional GitHub workflow:

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

Traffic uses the **existing GKE Gateway** (`demo-gateway` in `default` by
default). JobsRSS only adds an HTTPRoute; it does not create another Gateway
or touch nginx.

- Defaults: `JOBSRSS_GATEWAY_NAME=demo-gateway`,
  `JOBSRSS_GATEWAY_NAMESPACE=default`
- Hostname: `jobsrss.vincentspace.com` (override with `JOBSRSS_GATEWAY_HOST`)
- Point that name at the existing Gateway IP; demo `/` on the raw IP stays put
- `/` → frontend, `/healthz` `/jobs` `/rss` `/sources` → api

```bash
kubectl get gateway -A
kubectl -n jobsrss get httproute
kubectl -n jobsrss get pods
```

Portal: `http://jobsrss.vincentspace.com/`  
API health: `http://jobsrss.vincentspace.com/healthz`

## 7) First deployment checklist (Cloud Shell)

1. Open Cloud Shell, clone branch `cursor/jobs-intelligence-bootstrap-0a74`, `cd JobsRSS`.
2. Run `bootstrap-gcp.sh`.
3. Apply `.env.gke` secrets.
4. Run `cloud-shell-deploy.sh`.
5. Patch `ALLOWED_ORIGINS` / `RSS_BASE_URL` with the Gateway IP or domain.
6. Optional later: GitHub Actions or a managed certificate.

## 8) Jenkins alternative

`deploy/jenkins/Jenkinsfile.gke` uses the same scripts.

Jenkins credentials:

- `gcp-sa-key` (file)
- `gcp-project-id`, `gcp-region`, `gke-cluster`

## 9) Cloud SQL (optional later)

The in-cluster Postgres is the Compose-equivalent default. To move to Cloud SQL:

1. Create Cloud SQL Postgres 16.
2. Run Cloud SQL Auth Proxy as a sidecar or use the built-in connector.
3. Point `DATABASE_URL` at the proxy/private IP.
4. Remove the `postgres` StatefulSet.

Do not store database credentials in git; keep using `jobsrss-env`.
