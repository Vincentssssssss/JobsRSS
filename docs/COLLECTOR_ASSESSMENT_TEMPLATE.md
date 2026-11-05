# Collector Assessment Template

Use this template before implementing any new source collector.

## Source Metadata

- Source name:
- Source type: (company_site / job_platform / email)
- Owner team:
- Assessment date:

## Access and Endpoint Discovery

- Primary URL:
- Candidate API endpoints:
- Candidate JSON endpoints:
- RSS/Atom availability:
- Sitemap availability:

## Collection Method Decision

Priority order (must document what was checked):

1. Official API
2. JSON endpoint
3. RSS/Atom
4. Sitemap
5. Server-rendered HTML
6. Browser automation
7. Headless browser fallback

- Selected method:
- Why selected:
- Why higher-priority options were not feasible:

## Data Extraction

- Fields extracted:
  - source_job_id
  - company
  - title
  - location
  - country
  - description
  - apply_url
  - source_url
  - posted_at
- Field mapping notes:

## Search Configuration

- Keyword strategy:
- Location filters:
- Seniority filters:
- Negative filters:

## Operational Configuration

- Polling interval:
- Timeout:
- Retry policy:
- Rate limit policy:

## Compliance and Risk

- robots.txt / terms review result:
- Authentication requirement:
- Legitimate access plan:
- Known anti-bot constraints:

## Known Limitations

- Parsing fragility:
- Missing fields:
- Date quality:
- Apply-link quality:

## Test Plan

- Unit tests:
- Contract tests:
- Integration tests:
- Failure isolation behavior:

## Approval

- Reviewer:
- Approval date:
- Notes:
