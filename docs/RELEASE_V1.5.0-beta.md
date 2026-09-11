# JobsRSS v1.5.0-beta

## Status

Beta release for real-world LinkedIn and Liepin collection validation.

## Highlights

- LinkedIn authenticated job discovery using an exported browser session.
- Anchor-based LinkedIn parsing compatible with the current search result layout.
- Canonical LinkedIn job links with tracking parameters removed.
- Strict LinkedIn market allowlist:
  - Singapore
  - Hong Kong
  - Shanghai
  - Hangzhou
- LinkedIn title/company fallback extraction from job URL slugs.
- Official ATS enrichment for:
  - Workday
  - Greenhouse
  - Lever
  - SmartRecruiters
  - SuccessFactors
- Liepin authenticated collection with site-scoped Cookie refresh tooling.
- PostgreSQL normalization, deduplication, score calculation, and history.
- RSS feeds, web portal, full job details, direct application links, and daily
  24-hour digest support.

## Beta Constraints

- LinkedIn and Liepin may change page structure without notice.
- Authenticated sessions must be refreshed when a platform expires them.
- External enrichment is restricted to recognized ATS domains.
- 51job remains disabled by default.
- No automatic application submission is performed.

## Configuration

```env
APP_VERSION=1.5.0-beta
LINKEDIN_AUTH_ENABLED=true
LINKEDIN_STRICT_LOCATION_FILTER=true
LINKEDIN_ALLOWED_LOCATIONS=Singapore,Hong Kong,Shanghai,Hangzhou
LIEPIN_AUTH_ENABLED=true
JOB51_AUTH_ENABLED=false
```

## Upgrade

```bash
git fetch origin cursor/jobs-intelligence-bootstrap-0a74
git checkout cursor/jobs-intelligence-bootstrap-0a74
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build --no-cache api worker frontend
docker compose up -d --force-recreate api worker frontend
```

Verify:

```bash
curl http://localhost:8000/healthz
```

Expected:

```json
{"status":"ok","version":"1.5.0-beta"}
```
