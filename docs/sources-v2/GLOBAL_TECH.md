# V2 Global Technology Source Assessment

Assessment date: 2026-08-21

## Amazon / AWS

- Official search: `https://www.amazon.jobs/en/search`
- Selected source:
  `GET https://www.amazon.jobs/en/search.json`
- Shanghai parameters:
  - `country=CHN`
  - `city=Shanghai`
  - `sort=recent`
  - paginated `offset` / `result_limit`
- Method: anonymous JSON.
- Identity: `id_icims`.
- Extracted fields: title, company, full/multi-location metadata, description,
  qualifications, posting date, official job/apply URL.
- Polling: every 6 hours with bounded pagination.
- Limitation: endpoint is public but undocumented; `locations` can contain a
  JSON-encoded string and must be decoded defensively.

## Google

- Official search:
  `https://www.google.com/about/careers/applications/jobs/results/?location=Shanghai%2C%20China&sort_by=date`
- Method: server-rendered search and detail HTML.
- Identity: numeric ID in `/jobs/results/{id}-{slug}`.
- Extracted fields: title, multi-location data, qualifications,
  responsibilities, description, apply URL.
- Polling: first Shanghai page only every 6 hours, newest first.
- Limitation: pagination is not crawled because Google robots policy disallows
  automated paginated Careers result crawling. Publication date may be absent.

## Microsoft

- Official search:
  `https://apply.careers.microsoft.com/careers?location=Shanghai`
- Selected search JSON:
  `GET https://apply.careers.microsoft.com/api/pcsx/search`
- Detail JSON:
  `GET https://apply.careers.microsoft.com/api/pcsx/position_details`
- Parameters include `domain=microsoft.com`, `location=Shanghai`,
  `sort_by=timestamp`, `start`, and `num`.
- Method: anonymous Eightfold PCSX JSON backed by SuccessFactors requisitions.
- Identity: Eightfold position ID; recruiter-facing ATS ID retained in payload.
- Extracted fields: title, normalized locations, timestamp, department, work
  mode, description, qualifications, role type, employment type, apply URL.
- Polling: every 6 hours with bounded pagination.
- Limitation: implementation API is undocumented and may change.

## Apple (Wave 2)

- Official search:
  `https://jobs.apple.com/en-us/search?location=shanghai-china-state157`
- Method selected for future wave: server-rendered HTML/hydration data.
- Identity: numeric `positionId`.
- JSON search exists but requires a CSRF token and initialized cookies.
- Limitation: Shanghai search includes broad China retail pipelines; detail
  location post-filtering is required.
