# JobsRSS v1.1.0

## Release Goal

Improve LinkedIn job discovery quality and enrich job records from authoritative
company career or applicant-tracking-system pages.

## Included

- LinkedIn job discovery accepts only canonical `/jobs/view/<id>` records.
- LinkedIn tracking parameters are removed from source URLs.
- Company names can fall back to the LinkedIn job URL slug.
- External Apply links are detected when LinkedIn exposes a public external URL.
- Official pages are parsed using `JobPosting` JSON-LD first.
- Generic DOM fallbacks support recognized ATS job pages.
- Supported ATS detection:
  - Workday
  - Greenhouse
  - Lever
  - SmartRecruiters
  - SuccessFactors
- Official values take priority for:
  - company
  - title
  - location
  - description
  - publication date
  - application URL
- Existing database rows are updated with enriched company, country, publication
  time, description, and official application URL.
- Enrichment rejects local/private URL targets.
- Live enrichment is restricted to recognized ATS domains; arbitrary company
  domains are not fetched in v1.1.0.

## Configuration

```env
APP_VERSION=1.1.0
LINKEDIN_EXTERNAL_ENRICHMENT_ENABLED=true
LINKEDIN_EXTERNAL_ENRICHMENT_TIMEOUT_SECONDS=20
LINKEDIN_STRICT_LOCATION_FILTER=true
LINKEDIN_ALLOWED_LOCATIONS=Singapore,Hong Kong,Shanghai,Hangzhou
```

## Upgrade

```bash
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build --no-cache api worker
docker compose up -d api worker
docker compose restart worker
```

Existing LinkedIn rows can be enriched in place on the next collector run when
their normalized content changes. For a completely clean validation run:

```bash
docker compose exec -T postgres \
  psql -U jobsrss -d jobsrss \
  -c "DELETE FROM jobs WHERE source='linkedin_auth';"
docker compose restart worker
```

## Known Limitations

- LinkedIn Easy Apply jobs may not expose an external company application URL.
- Some external career sites require JavaScript or block automated access; those
  jobs retain the LinkedIn details and application URL.
- Company-hosted career pages outside the recognized ATS allowlist are left for
  a future per-domain opt-in release.
- External enrichment does not submit applications.
