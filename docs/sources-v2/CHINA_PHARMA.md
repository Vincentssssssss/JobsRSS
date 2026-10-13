# V2 China Pharma Source Assessment

Assessment date: 2026-08-21

## WuXi AppTec

- Official China portal: `https://wuxiapptec.zhiye.com/social/jobs`
- ATS: Beisen/Zhiye.
- Selected source: `POST /api/Jobad/GetJobAdPageList`.
- Shanghai filter: `LocId=["3100"]`.
- Identity: job UUID (`Id`).
- List JSON includes full responsibilities and requirements.
- Live connector smoke test passed.

## WuXi Biologics

- Official China portal:
  `https://job.wuxibiologics.com.cn/social-recruitment/wuxibiologics/99960`
- ATS: Moka.
- Selected source: encrypted Moka list/detail JSON.
- AES parameters are dynamically read from portal `#init-data` and each API
  response; no key/IV is hardcoded.
- All jobs are paged conservatively and location-filtered locally.
- Live connector smoke test passed with Shanghai district locations.

## Hengrui Medicine

- Official careers page:
  `https://www.hengrui.com/development/recruit.html`
- No stable current first-party job inventory, API, or individual job pages.
- Status: registered and monitored, but not operational for job publication.
- Reason: publishing stale third-party/campus content would reduce data quality.

## Fosun Pharma

- Official portal: `https://fosunpharma.zhiye.com/social`
- ATS: legacy Beisen/Zhiye server-rendered HTML.
- Shanghai filter: `c=3100`, paginated by `PageIndex`.
- Detail identity: numeric `jobId`.
- Detail HTML includes member company, publication date, location,
  responsibilities, and qualifications.
- Live connector smoke test passed.

## Chia Tai Tianqing

- Official portal: `https://cttq.zhiye.com/social`
- ATS: Beisen/Zhiye.
- Selected source: `POST /api/Jobad/GetJobAdPageList`.
- Shanghai filter: `LocId=["3100"]`.
- Posting date falls back to `ChangeDate` when the source emits year 0001.
- Live connector smoke test passed.

## Yunnan Baiyao

- Official vanity URL: `https://zhaopin.ynby.cn/`
- ATS: HotJob at `https://wecruit.hotjob.cn`.
- Selected list/detail JSON endpoints under tenant
  `SU6136b970bef57c3b638162c4`.
- Server-side location filter serialization is unreliable, so the connector
  scans the bounded social listing and filters location locally.
- Explicit non-Shanghai cities are excluded; broad China/APAC/Remote values
  remain unclassified.
