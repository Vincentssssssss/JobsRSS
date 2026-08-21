# V2 International Pharma Source Assessment

Assessment date: 2026-08-21

## GSK

- Global careers: `https://jobs.gsk.com/gb/en/search-results`
- China careers: `https://app.mokahr.com/social-recruitment/gsk/148067`
- Recommended source: China Moka board because the global board is incomplete
  for Mainland China.
- Shanghai location IDs must be discovered from Moka filter aggregations.
- Moka list/detail APIs return an encrypted frontend envelope.
- Status: implementation pending verified decryption contract.
- Fallbacks: GSK Workday and official sitemap for reconciliation only.

## Roche

- Official search: `https://careers.roche.com/global/en/search-results`
- Selected source:
  `POST https://careers.roche.com/widgets`
- Search mode: Phenom `refineSearch`.
- Shanghai filters:
  - country: `China's Mainland`
  - city: `Shanghai`
- Detail mode: Phenom `jobDetail`, keyed by `jobId` and `jobSeqNo`.
- Extracted fields: title, full HTML description, locations, publication date,
  job level/category, apply URL, requisition metadata.
- Identity: `jobSeqNo`.
- Polling: every 6 hours in V2 with bounded result size.
- Limitation: public but undocumented JSON contract; tolerate schema changes.
- Live connector smoke test passed with full descriptions and confirmed
  Shanghai locations.
