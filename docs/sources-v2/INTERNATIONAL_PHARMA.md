# V2 International Pharma Source Assessment

Assessment date: 2026-08-21

## GSK

- Global careers: `https://jobs.gsk.com/gb/en/search-results`
- China careers: `https://app.mokahr.com/social-recruitment/gsk/148067`
- Recommended source: China Moka board because the global board is incomplete
  for Mainland China.
- Shanghai location IDs are applied to the Moka list request.
- Moka list/detail APIs return an AES-128-CBC encrypted frontend envelope.
- The IV is read dynamically from portal `#init-data`; each response supplies
  its own key. No cryptographic material is hardcoded.
- Live connector smoke test passed with Shanghai/Pudong jobs.
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
