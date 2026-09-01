# JobsRSS v2.1.0

## Release Focus

Expand the official company registry for the next sourcing wave while keeping
the existing production collectors stable.

## Registry Expansion

- Registry size expanded from **38** to **49** official company sources.
- First-wave production scope remains unchanged:
  - 16 approved first-wave sources,
  - 15 operational first-wave collectors,
  - Hengrui remains monitor-only due to missing stable inventory.

### Added in v2.1.0

Requested companies:

- Weiermei / 味儿美 (`weiermei`)
- Yunnan Baiyao / 云南白药 (`yunnan_baiyao`, existing first-wave operational source retained)
- Innovent Biologics / 信达生物 (`innovent`)
- Simcere / 先声药业 (`simcere`)

Mainstream private enterprise expansion (technology):

- Ant Group / 蚂蚁集团 (`ant_group`)
- JD.com / 京东 (`jd`)
- Meituan / 美团 (`meituan`)
- PDD / 拼多多 (`pdd`)
- DiDi / 滴滴 (`didi`)
- Kuaishou / 快手 (`kuaishou`)
- NetEase / 网易 (`netease`)
- Bilibili / 哔哩哔哩 (`bilibili`)
- Trip.com / 携程 (`trip_com`)
- Xiaohongshu / 小红书 (`xiaohongshu`)

## Operational Notes

- Newly added v2.1 sources are registered as second-wave candidates
  (`assessment_pending`) by default.
- This release intentionally separates **registry expansion** from
  **collector implementation** to reduce production risk.

## UI / API Improvements

- Added `GET /jobs/source-counts` aggregation endpoint to return grouped
  source counts under current filters.
- Source dropdown now shows per-source counts (for example
  `official_xiaomi (12)`), plus an aggregate `All sources (N)` label.
- This helps quickly distinguish:
  - source exists but current filters produce zero matches,
  - source catalog failed to load.

## Version Metadata

- Backend default `APP_VERSION=2.1.0`
- Frontend package version `2.1.0`

## Upgrade

```bash
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build --no-cache api worker frontend
docker compose up -d --force-recreate api worker frontend
```
