# JobsRSS DevOps Pipeline (GitHub Actions + Azure VM)

This guide sets up a near-production CI/CD flow:

1. Run CI on every PR/push.
2. Build backend/frontend container images.
3. Push images to Azure Container Registry (ACR).
4. Deploy on an Azure VM with Docker Compose.

## 1) Repository files added

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-azure-vm.yml`
- `deploy/azure/vm/docker-compose.prod.yml`
- `deploy/azure/vm/deploy.sh`
- `deploy/azure/vm/.env.prod.example`

## 2) Azure prerequisites

Create and prepare:

- 1 resource group
- 1 Azure Container Registry (ACR)
- 1 Linux VM (Ubuntu recommended)
- VM software: Docker Engine + Docker Compose plugin + curl

On the VM:

```bash
sudo mkdir -p /opt/jobsrss/secrets
sudo chown -R "$USER":"$USER" /opt/jobsrss
cp /opt/jobsrss/.env.prod.example /opt/jobsrss/.env.prod
```

Fill `/opt/jobsrss/.env.prod` with production values.

Put authenticated session files under `/opt/jobsrss/secrets` when needed:

- `/opt/jobsrss/secrets/linkedin_state.json`
- `/opt/jobsrss/secrets/liepin_state.json`

## 3) GitHub secrets required

Configure these repository secrets:

- `AZURE_CREDENTIALS` (service principal JSON for `azure/login`)
- `ACR_NAME` (for `az acr login`)
- `ACR_LOGIN_SERVER` (example: `myregistry.azurecr.io`)
- `ACR_USERNAME`
- `ACR_PASSWORD`
- `AZURE_VM_HOST`
- `AZURE_VM_USER`
- `AZURE_VM_SSH_KEY` (private key PEM content)
- `AZURE_VM_PORT` (optional, default 22)

## 4) CI behavior

Workflow: `.github/workflows/ci.yml`

- Backend tests: `PYTHONPATH=backend pytest backend/tests`
- Frontend build: `npm ci && npm run build`

Runs on:

- pull requests
- pushes to `main` and `cursor/**`

## 5) CD behavior

Workflow: `.github/workflows/deploy-azure-vm.yml`

Triggers:

- Push to `main`
- Manual run (`workflow_dispatch`)

Stages:

1. Build/push `jobsrss-api` and `jobsrss-frontend` images to ACR.
2. Copy deploy assets to `/opt/jobsrss` on VM.
3. Execute `/opt/jobsrss/deploy.sh` on VM.

The deploy script:

- Merges `.env.prod` with runtime image metadata
- Pulls images
- Runs `docker compose up -d --remove-orphans`
- Verifies `http://127.0.0.1:8000/healthz`

## 6) First deployment checklist

1. Merge pipeline files to `main`.
2. Prepare VM `.env.prod` and secrets files.
3. Set GitHub secrets.
4. Run `Deploy to Azure VM` workflow manually once.
5. Verify:
   - `https://<vm-or-domain>:3000`
   - `https://<vm-or-domain>:8000/healthz` (or via reverse proxy)

## 7) Optional Jenkins alternative

If you prefer Jenkins:

- Reuse the same deploy assets under `deploy/azure/vm/`.
- A ready template is provided at `deploy/jenkins/Jenkinsfile.azure`.
- Pipeline stages should match:
  - checkout
  - backend tests
  - frontend build
  - docker build/push to ACR
  - SSH deploy (`bash /opt/jobsrss/deploy.sh`)

GitHub Actions can remain your default while Jenkins is added later for
enterprise orchestration or multi-repo governance.
