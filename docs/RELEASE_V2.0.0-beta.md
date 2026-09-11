# JobsRSS v2.0.0-beta

## Release Goal

Monitor official company career sites for Shanghai roles and broad
China/APAC/Remote roles whose city is not yet classified.

## Registry

- 38 approved official company sources.
- 16 first-wave sources.
- 15 operational first-wave collectors.
- Hengrui remains monitored but does not publish jobs because no stable,
  current first-party inventory is available.

## Operational First-Wave Connectors

Technology:

- Amazon / AWS — Amazon Jobs JSON
- Google — first-page SSR/hydration and detail HTML
- Microsoft — Eightfold PCSX JSON
- Alibaba / Alibaba Cloud — XSRF-protected campus JSON
- Tencent / Tencent Cloud — careers JSON
- Huawei / Huawei Cloud — API Gateway JSON
- Xiaomi — Feishu Recruiting JSON
- ByteDance — Feishu-compatible recruiting JSON

Pharma, biotech, and CRO/CDMO:

- WuXi AppTec — Beisen/Zhiye JSON
- WuXi Biologics — encrypted Moka JSON
- Fosun Pharma — Shanghai-filtered server-rendered HTML
- Chia Tai Tianqing — Beisen/Zhiye JSON
- Yunnan Baiyao — HotJob list/detail JSON with local location filtering
- GSK — encrypted Moka JSON
- Roche — Phenom search/detail JSON

## Location Policy

- `confirmed_shanghai`: explicitly includes Shanghai.
- `unclassified`: China, Mainland China, Greater China, APAC, Asia Pacific,
  Remote, or missing location.
- `excluded`: explicit non-Shanghai city without Shanghai.

Only confirmed Shanghai and unclassified jobs enter the database/publication
pool.

## Safety and Reliability

- Official APIs/JSON are preferred over HTML and browser automation.
- No CAPTCHA, authentication, rate-limit, or anti-bot bypass.
- Bounded per-source collection and six-hour default polling.
- Each source runs as an isolated APScheduler job.
- 429/5xx retry support where required.
- Moka AES keys and IVs are read dynamically; no secrets are hardcoded.
- Hengrui stale/third-party listings are deliberately not published.

## Configuration

```env
APP_VERSION=2.0.0-beta
OFFICIAL_SOURCES_ENABLED=true
OFFICIAL_SOURCE_INTERVAL_MINUTES=360
OFFICIAL_SOURCE_TIMEOUT_SECONDS=30
OFFICIAL_SOURCE_MAX_JOBS_PER_SOURCE=50
OFFICIAL_SOURCE_MAX_PAGES_PER_SOURCE=10
OFFICIAL_SOURCE_STALE_AFTER_DAYS=30
OFFICIAL_SOURCE_VERIFY_TLS=true
```

## Upgrade

```bash
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build --no-cache api worker frontend
docker compose up -d --force-recreate api worker frontend
```

Verify:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/sources/official
```
