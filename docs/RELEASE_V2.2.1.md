# JobsRSS v2.2.1

## Release Focus

Search and filter jobs by place, whatever language or format a source uses
for its locations. Sources write the same city many ways (`上海`,
`Shanghai, China`, `Shanghai, Shanghai, CHN`, `浦东新区`, `SH`). This release
maps each listing to one canonical city and country, so a search for any of
these spellings finds the same jobs.

Changes since v2.2.0: 7 commits. Patch release; the schema change applies
automatically on start.

## Highlights

### Location standardization

- Every job gets a standardized city list and country (stored in the new
  `location_cities` column and the existing `country` column). The table
  covers Chinese, English and pinyin names, Shanghai and Jiangsu/Zhejiang
  districts, ISO country codes and common city codes (SH, HK, KL, SG, HCMC).
- Multi-location listings keep every city (for example
  `上海市, 杭州市, 苏州市` stores Shanghai, Hangzhou and Suzhou). Before, a
  Shanghai row kept only `上海`, so its other cities were not searchable.
- Rows stored by older versions are standardized when the api or worker
  starts. No re-collection is needed.

### Search

- The search box understands place names. `上海`, `Shanghai` and `SH` return
  the same jobs; so do `香港` / `Hong Kong` / `HK` and `吉隆坡` /
  `Kuala Lumpur` / `KL`. A country name (`马来西亚`, `Malaysia`, `新加坡`)
  matches every job in that country.
- Words are combined with AND: `安全 杭州` finds security jobs in Hangzhou,
  and `上海安全` works without a space.
- Place words still match title, company and location text too, so `上海`
  also finds a job titled "上海区域销售经理" even if its listing names
  another city.

### Dashboard

- A **Location** picker lists countries and their cities with job counts for
  the current filters, including an "All of <country>" option.
- Cards show the standardized place (`上海 Shanghai · 中国 China`); hovering
  shows the original text, and the detail panel shows "Listed as: …".
- **Location Classification** is now **Target Region** and adds
  "Outside target areas".
- Typing in the search box waits 300 ms before querying, and responses for an
  earlier filter state are ignored. Before, every keystroke sent a full set of
  requests, and a slow, older response could overwrite newer results.

### API

- `GET /jobs`, `/jobs/count` and `/jobs/source-counts` accept `city` and
  `country` (comma-separated; any alias works, for example `city=上海`).
- New `GET /jobs/locations` returns countries and cities with counts.
- Job responses include `country`, `cities` and `location_label`.

### Classification fixes

- Chongqing's 九龙坡 district was classified as Hong Kong (it contains
  九龙, Kowloon). It is now "Outside target areas".
- More Jiangsu/Zhejiang cities are recognized as Jiangsu/Zhejiang: Taicang,
  Xuzhou, Yangzhou, Zhenjiang, Yancheng, Huai'an, Lianyungang, Suqian,
  Taizhou, Jinhua/Yiwu, Quzhou and Lishui. Jobs in these cities can now pass
  the target-region filter.
- LinkedIn, Liepin and 51job rows get a target region like official rows.
  Before, they were left unclassified.
- Every stored row is reclassified at startup, so classifier fixes reach
  existing jobs.

## Upgrade

From v2.2.0 or earlier:

```bash
cd ~/JobsRSS
git pull
docker compose up -d --force-recreate api worker
docker compose build frontend && docker compose up -d frontend
scripts/smoke_test.sh
```

The api and worker log `locations_standardized count=N` on their first start
(N is about the number of stored jobs), then a small number on later starts.

## Test Report

All runs were on 2026-11-04 from a US-based test VM with live access to every
career site. LLM rerank was off (the default). Each row names the commit it ran
on; later commits changed only what the "Found and fixed" list describes.

| Area | Commit | What ran | Result |
|---|---|---|---|
| Unit and integration tests | `608129f` | `pytest backend/tests` | 303 passed (242 in v2.2.0) |
| Frontend typecheck | `608129f` | `npx tsc --noEmit` | passed |
| Location strings from every source | `608129f` | Rows from a live run of all 23 official collectors: 2,973 rows, 314 distinct location strings, mapped and reviewed by hand | Every string that names a city maps to it. 115 rows have no city; they list only a country or country code, `中国`, `江苏省` or `Unknown`. No standardized city disagrees with its target region |
| Upgrade from v2.2.0 | `v2.2.0` to `343e9bd` | v2.2.0 stack collected all 23 sources (1,958 active jobs), plus 8 LinkedIn/Liepin/51job rows and a favorite; then `git pull`, recreate, frontend rebuild | `/healthz` 2.2.1, 2,866 rows standardized, favorite kept, platform rows classified (Beijing row is "Outside target areas") |
| Search by place | `343e9bd` | Same query in each spelling, `/jobs/count` | 上海 1,024 / Shanghai 1,026 / SH 1,024; 香港, Hong Kong, HK 135 each; 吉隆坡, Kuala Lumpur, KL 32 each; 新加坡, Singapore 234 each; 马来西亚, Malaysia 119 each. Before the upgrade: 上海 1,023 vs Shanghai 106, 杭州 205 vs Hangzhou 8 |
| Startup reclassification | `ed7b28e` | api and worker recreated | 2 rows changed (the 九龙坡 rows); all others already agreed |
| Collection cycle | `ed7b28e` | Worker ran all 23 official sources | 23 collected, 0 errors, 1,965 active jobs. Hangzhou rose from 184 to 222 as multi-city listings were re-stored |
| Smoke test | `608129f` | `scripts/smoke_test.sh --write` | 51 passed, 0 failed, 1 warning (LLM off) |
| Dashboard | `ed7b28e`, `608129f` | Browser run: Location picker (Hangzhou, Kuala Lumpur), search by keyword and city, cards and detail panel; fast typing of `Hong Kong` | all steps passed; the API received one request for the finished query instead of one per keystroke |

Found and fixed during testing:

- `Putuo District, Zhoushan` was read as Shanghai (Shanghai also has a Putuo
  district). A city named in a listing now wins over a district name.
- `Boise, ID, US` was read as Indonesia. Two-letter country codes now count
  only at the end of a listing.
- Searching a province (`浙江`) would have matched every job in China.
  Provinces now match as text only.
- The 九龙坡 classifier bug above, and the startup step that reclassified
  only unclassified rows (`ed7b28e`).
- Per-keystroke request bursts and out-of-order responses in the dashboard
  (`608129f`).

## Known Issues

- Districts (`浦东`) and provinces (`江苏`) match job text only; they do not
  expand to a city or province filter. Use the city name instead.
- Keywords are not translated: `security` does not match `安全`. Search in
  the language the posting uses, or both.
- Jobs whose source gives no place (`Unknown`), only a country or only a
  province have no city; country-only rows still match a country search.
  The Location picker shows how many.
- Known issues from v2.2.0 still apply (Google TLS resets from mainland China
  networks, Alibaba detail links outside China, assessment-pending sources).
