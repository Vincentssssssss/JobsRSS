# JobsRSS V2.0 Official Career Sources Implementation Plan

## Goal

Add a maintainable official-company career collection subsystem backed by a
38-company registry, with 16 approved first-wave connectors.

## First Wave

Technology:

- Amazon / AWS
- Google
- Microsoft
- Alibaba / Alibaba Cloud
- Tencent / Tencent Cloud
- Huawei / Huawei Cloud
- Xiaomi
- ByteDance

Pharma and biotech:

- WuXi AppTec
- WuXi Biologics
- Hengrui Medicine
- Fosun Pharma
- Chia Tai Tianqing
- Yunnan Baiyao
- GSK
- Roche

## Location Publication Policy

- `confirmed_shanghai`: job location explicitly includes Shanghai/上海.
- `unclassified`: job location is empty, Unknown, China, Mainland China,
  Greater China, APAC, Asia Pacific, Remote, 中国, 全国, 亚太, or 大中华.
- `excluded`: an explicit non-Shanghai city without Shanghai in the location.

Only `confirmed_shanghai` and `unclassified` jobs enter the publication pool.

## Architecture

```text
Official source registry
  -> Source-specific discovery adapter
  -> Official detail parser
  -> Location classifier
  -> UnifiedJob
  -> Existing normalization/dedup/matching pipeline
  -> PostgreSQL / RSS / Portal / Digest
```

## Collection Priority

Every first-wave source must document checks in this order:

1. Official API
2. Public JSON endpoint
3. RSS/Atom
4. Sitemap
5. Server-rendered HTML
6. Browser automation
7. Headless-browser fallback

## Implementation Tasks

### 1. Registry and classification

- Register all 38 approved sources.
- Enable only the 16 first-wave sources.
- Add deterministic location classification and tests.

### 2. Source assessment

- Record official URL, endpoints, extraction method, fields, rate, and
  limitations for every first-wave source.
- Do not claim an endpoint is stable without direct evidence.

### 3. Connector framework

- Add a common official-career collector contract.
- Support structured JSON and JSON-LD/HTML adapters.
- Use browser automation only for sources that require rendered content.
- Keep individual source parsing configuration out of core pipeline logic.

### 4. Persistence and publication

- Persist source provenance and location classification.
- Preserve official application URLs.
- Publish `confirmed_shanghai` and visibly labelled `unclassified` jobs.
- Exclude explicit non-Shanghai locations.

### 5. Scheduling and observability

- Schedule each source independently.
- Keep per-source failure isolation.
- Log start/end/found/new/duplicates/errors.
- Use conservative intervals and no CAPTCHA/anti-bot bypass.

### 6. Verification

- Registry contract tests.
- Location classifier tests.
- Fixture-based parser tests for each adapter family.
- Scheduler isolation tests.
- RSS/API tests for location category behavior.

## Release Target

`v2.0.0-beta`
