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
bash deploy/gke/scripts/write-env-gke.sh
# writes ~/jobsrss.env.gke — Cloud Shell /tmp is wiped
nano ~/jobsrss.env.gke   # paste LLM_API_KEY
bash deploy/gke/scripts/apply-secrets.sh ~/jobsrss.env.gke
```

Hostname routing is **not** in this env file. `jobsrss.vincentspace.com` is set on
the HTTPRoute. If the domain still opens the demo app **and** pods already exist,
apply the route:

```bash
export JOBSRSS_GATEWAY_HOST=jobsrss.vincentspace.com
bash deploy/gke/scripts/apply-route.sh
kubectl -n jobsrss describe httproute jobsrss
```

`/path/to/secrets` is optional. If present it may contain:

- `linkedin_state.json`
- `liepin_state.json`

Those files are merged into Secret `jobsrss-collector-files` and mounted at
`/secrets` (read-only). Uploading only one file keeps the other cookie.

To enable both platforms on GKE after the files are in `~/secrets`:

```bash
sed -i 's/^LINKEDIN_AUTH_ENABLED=.*/LINKEDIN_AUTH_ENABLED=true/' ~/jobsrss.env.gke
sed -i 's/^LIEPIN_AUTH_ENABLED=.*/LIEPIN_AUTH_ENABLED=true/' ~/jobsrss.env.gke
bash deploy/gke/scripts/apply-secrets.sh ~/jobsrss.env.gke ~/secrets
kubectl -n jobsrss rollout restart deploy/api deploy/worker
```

GKE datacenter IPs are often blocked by LinkedIn/Liepin even with a valid
session file. Kubernetes does not strip cookies from the mounted Secret; the
usual failures are a disabled flag, a missing `~/secrets/*.json` filename, or
the site rejecting the cluster egress IP.

```bash
bash deploy/gke/scripts/check-collectors.sh
```

### Simplest path: drive the in-cluster browser from your own machine

The browser stays in the cluster, so LinkedIn sees the GKE egress IP. Your
laptop is only the screen. This needs `kubectl` and a browser, no Playwright
locally, and no `~/jobsrss.env.gke` on that machine.

```bash
gcloud auth login            # must be the account that can read the cluster
gcloud config set account <that-account>
gcloud container clusters get-credentials asp-gke-dev-gke-d9df \
  --zone=asia-southeast1-a --project=gcp-bcgx-dev-vincents-d597

bash deploy/gke/scripts/cookie-to-k8s.sh desktop     # leave running
# local browser -> http://127.0.0.1:6080/   (fallback http://127.0.0.1:8080/)
# log in until the feed loads, then Ctrl+C

bash deploy/gke/scripts/cookie-to-k8s.sh from-pod
bash deploy/gke/scripts/cookie-to-k8s.sh check
```

Minting on the laptop instead (`cookie-to-k8s.sh all`) works mechanically but
uses the laptop IP, which LinkedIn usually rejects once the worker reuses the
cookie. On Homebrew Python, install Playwright in a venv and pass
`PYTHON_BIN=~/.jobsrss-venv/bin/python`.

It patches `jobsrss-collector-files`, sets the matching `*_AUTH_ENABLED`
flag in `jobsrss-env`, and restarts the worker, which then refreshes jobs on
its own schedule until the cookie expires. Re-run the same command to renew.

A laptop-minted LinkedIn cookie used from GKE often still yields `found=0`
(datacenter ASN). Minting the session **on the same cluster egress IP** is
the in-cluster alternative below. It is interactive and still not
guaranteed — LinkedIn can checkpoint Google Cloud IPs.

Use the PR branch (plain `git pull` on `main` stays "Already up to date"
and keeps the old login scripts):

```bash
git fetch origin
git checkout cursor/jobs-intelligence-bootstrap-0a74
git reset --hard origin/cursor/jobs-intelligence-bootstrap-0a74
export IMAGE_API=asia-southeast1-docker.pkg.dev/$GCP_PROJECT_ID/jobsrss/jobsrss-api:2adea08
bash deploy/gke/scripts/linkedin-session.sh start
```

`start` Cloud Builds `jobsrss-linkedin-login` (xvfb/x11vnc/novnc on top of
`jobsrss-api:2adea08`). Do not `docker build` that image in Cloud Shell.
Runtime `apt-get` inside the login pod is what caused CrashLoopBackOff
(`6080 connection refused` then kubelet restart).

Wait until the first terminal prints `NOVNC_READY`. Only then, in another tab:

```bash
bash deploy/gke/scripts/linkedin-session.sh port-forward
```

That forwards the Ready pod (8080 HTTP login + 6080 noVNC), not
`svc/linkedin-login`.

Do **not** edit the Cloud Shell Web Preview address bar. Preview resets
custom paths back to `/`, which looks like a blank spinning page.
Prefer Web Preview port **8080** (screenshot + login form). Port 6080 is
the desktop; Cloud Shell often cannot proxy its WebSocket.

```bash
bash deploy/gke/scripts/linkedin-session.sh --export
bash deploy/gke/scripts/linkedin-session.sh stop
```

Cloud Shell Web Preview cannot show this desktop: it resets custom paths to
`/` and does not proxy the noVNC WebSocket. Any interactive session needs a
browser or RDP client outside Cloud Shell.

### Option A: laptop browser into the Linux pod (no new infrastructure)

```bash
gcloud container clusters get-credentials asp-gke-dev-gke-d9df \
  --zone=asia-southeast1-a --project=$GCP_PROJECT_ID
kubectl -n jobsrss port-forward deploy/linkedin-login 6080:6080 8080:8080
```

Open `http://127.0.0.1:6080/` in the laptop browser for the full noVNC
desktop (real mouse and keyboard). `http://127.0.0.1:8080/` is the fallback
form. Then `linkedin-session.sh --export`.

### Option B: Windows desktop VM

Windows **containers do not support RDP or GUI** — Microsoft removed both by
design — so a Windows node pool or "Windows pod" cannot give an interactive
desktop. Use a Windows VM in the existing VPC instead. Placing it on the GKE
subnet with no external IP makes it share the same Cloud NAT egress IP as the
worker.

```bash
bash deploy/gke/scripts/windows-login-vm.sh create
bash deploy/gke/scripts/windows-login-vm.sh password   # copy it once
bash deploy/gke/scripts/windows-login-vm.sh tunnel     # on your laptop
# Microsoft Remote Desktop -> 127.0.0.1:13389
# desktop icons: 1-start-linkedin-login.bat, then 2-export-cookies.bat
bash deploy/gke/scripts/windows-login-vm.sh export
bash deploy/gke/scripts/windows-login-vm.sh delete
```

The VM bills Windows licensing while it runs. Delete it once the cookie is
exported.

## Pause worker / save Azure LLM spend

LLM scoring only runs in `deploy/worker`. Scaling it to 0 stops collectors
and Azure calls. The portal stays up.

```bash
bash deploy/gke/scripts/jobsrss-control.sh status
bash deploy/gke/scripts/jobsrss-control.sh worker-stop   # no collect, no LLM
bash deploy/gke/scripts/jobsrss-control.sh worker-start
bash deploy/gke/scripts/jobsrss-control.sh llm-off       # collect, but no Azure
bash deploy/gke/scripts/jobsrss-control.sh llm-on
```

This is a Linux GUI pod (Xvfb + noVNC), not a headless collector. Do not add a
Windows node pool for LinkedIn: GKE Windows egress is still a Google Cloud IP.

The login Service is ClusterIP only. Do not attach it to `demo-gateway`.
CI never overwrites `jobsrss-env`; missing that secret fails the deploy on
purpose.

`apply-secrets.sh` only writes Secrets. It does **not** create
`api` / `frontend` / `worker` / `postgres`. Do not
`kubectl rollout restart deploy/worker` until those Deployments exist.

After the first successful `cloud-shell-deploy.sh`, if you later change
`ALLOWED_ORIGINS` or `RSS_BASE_URL` in `~/jobsrss.env.gke`, re-run
`apply-secrets.sh`, then:

```bash
kubectl -n jobsrss rollout restart deploy/api deploy/frontend deploy/worker
```

## 4) Deploy from Cloud Shell

After secrets exist, this is the step that actually creates pods:

```bash
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=asia-southeast1
export GKE_CLUSTER=your-existing-cluster-name
export JOBSRSS_GATEWAY_NAME=demo-gateway
export JOBSRSS_GATEWAY_NAMESPACE=default
export JOBSRSS_GATEWAY_HOST=jobsrss.vincentspace.com
bash deploy/gke/scripts/cloud-shell-deploy.sh
```

This submits `deploy/gke/cloudbuild.yaml` (backend + frontend in parallel),
then `kubectl apply` to the existing cluster. Backend image build can take
15–30 minutes because of Playwright.

To ship a frontend-only change without rebuilding the Playwright API image:

```bash
export IMAGE_API_TAG=2adea08
export SKIP_API_BUILD=1
bash deploy/gke/scripts/cloud-shell-deploy.sh
```

If Cloud Build already succeeded and only `kubectl apply -k` failed, reuse
the built tag instead of rebuilding:

```bash
export IMAGE_TAG=2adea08   # the tag Cloud Build printed as SUCCESS
export SKIP_CLOUD_BUILD=1
bash deploy/gke/scripts/cloud-shell-deploy.sh
```

Enterprise projects often disable the default Compute service account
(`…-compute@developer.gserviceaccount.com`). The deploy script creates and
uses `jobsrss-cicd@…` instead — do not enable the default Compute SA.

Check the load balancer and workloads:

```bash
kubectl -n default get gateway demo-gateway
kubectl -n jobsrss get httproute jobsrss
kubectl -n jobsrss get pods
```

Portal: `http://jobsrss.vincentspace.com/`  
API health: `http://jobsrss.vincentspace.com/healthz`  
The raw Gateway IP still serves the existing demo app.

If the hostname returns `500 fault filter abort`, Kubernetes pods can be
Running while the Gateway health check is still failing. GKE probes the
**pod IP** (not the Service), so the API must pass `GET /healthz` on
container port 8000 and the frontend must pass `GET /` on container port
3000. Re-apply workloads (no image rebuild) and wait 1–2 minutes:

```bash
export IMAGE_TAG=2adea08
export SKIP_CLOUD_BUILD=1
bash deploy/gke/scripts/cloud-shell-deploy.sh
kubectl -n jobsrss describe httproute jobsrss
```

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
kubectl -n jobsrss get httproute jobsrss
kubectl -n jobsrss get pods
```

Portal: `http://jobsrss.vincentspace.com/`  
API health: `http://jobsrss.vincentspace.com/healthz`

## 7) First deployment checklist (Cloud Shell)

1. Open Cloud Shell, clone branch `cursor/jobs-intelligence-bootstrap-0a74`, `cd JobsRSS`.
2. Run `bootstrap-gcp.sh`.
3. Apply `.env.gke` secrets (`secret/jobsrss-env` only — no pods yet).
4. Run `cloud-shell-deploy.sh` (this creates postgres/api/frontend/worker).
5. Confirm `kubectl -n jobsrss get pods` shows Running, then open
   `http://jobsrss.vincentspace.com/`.
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
