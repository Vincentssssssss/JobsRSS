# V2 China Technology Source Assessment

Assessment date: 2026-08-21

No documented public careers API, RSS/Atom feed, or useful jobs sitemap was
found for these companies. The selected sources are undocumented first-party
web APIs and must be monitored for schema changes.

## Alibaba Group and Alibaba Cloud

Two sources share one collector module (`official/collectors/alibaba.py`):

| Source | Portal | Company label |
| --- | --- | --- |
| `official_alibaba` | `https://talent.alibaba.com/off-campus/position-list?lang=zh` | Alibaba Group / 阿里巴巴集团 |
| `official_aliyun` | `https://careers.aliyun.com/off-campus/position-list?lang=zh` | Alibaba Cloud / 阿里云 |

Shared platform facts (both hosts, social recruitment; the campus portal is no
longer collected):

- Search: `POST {host}/position/search` with
  `{"channel", "language", "key", "pageIndex", "pageSize"}` plus optional
  `subCategories` and `regions` (comma-joined codes). `pageSize` 100 works.
  A query returns at most 500 rows; later pages come back empty.
- Channels: `group_official_site` (`language: zh`) and
  `group_overseas_official_site` (`language: en`) on both hosts. On
  `careers.aliyun.com` the host itself scopes results to Alibaba Cloud
  (circle `60002`); its page config also names `aliyun_group_official_site`,
  which only the detail call uses.
- XSRF: `GET` the portal page (answers 302) to receive the `XSRF-TOKEN`
  cookie, then send it as `X-XSRF-TOKEN` with a portal `Referer`.
- `key` matches title words only (tokenised, so "云安全" and "安全架构"
  return subsets of "安全"). The security category is `subCategories: "407"`
  (技术类 > 安全); it is applied to few roles but catches 防御 / 漏洞 / 合规
  titles. Region codes: Shanghai `310100`, Hangzhou `330100`, Beijing
  `110100`, Hong Kong `HKG`; overseas: Singapore `SINGAPORE`, Kuala Lumpur
  `MYSKLKLKUL`.
- Rows include `description`, `requirement`, `workLocations` (city names),
  `experience.from`, `publishTime`; no detail call is needed.
  `POST /position/detail` returned an empty object for every payload tried
  (both channels, with the page `_csrf` token).
- Detail pages: `{host}/off-campus/position-detail?positionId={id}` (zh) and
  `{host}/en/off-campus/position-detail?positionId={id}` (en). On
  `careers.aliyun.com` both render the exact job (the en page may redirect to
  `careers.alibabacloud.com`). From a US network on 2026-10-13, every
  `talent.alibaba.com/off-campus/...` page, including the list, 302'd to the
  group homepage.

Ownership and dedupe:

- `talent.alibaba.com` lists every Alibaba Cloud role under the same position
  id as `careers.aliyun.com` (in all 12 compared queries every aliyun result
  was also in the talent result). `official_alibaba` therefore runs the aliyun collector,
  skips the ids it returns, and lists the talent URLs of skipped roles in
  `retired_source_url_prefixes` so rows it stored for them earlier close on
  the same run.
- `official_aliyun` searches "安全", the security category, "技术服务"
  (TAM / technical service), "解决方案", "架构师", then overseas "security"
  and "architect", and finally sweeps every Shanghai role (`regions: 310100`)
  and every overseas role. Keyword groups come first in the round-robin cap so
  relevant roles are never the ones cut.
- `official_alibaba` searches "安全" and "security" (zh), "security" (en) and
  the security category on both channels.

Live inventory (2026-10-13):

- `careers.aliyun.com`: 693 China + 239 overseas roles. China by region:
  Hangzhou 475, Beijing 283, Shanghai 129, Hong Kong 1. Overseas cities:
  Sunnyvale 27, Hong Kong 22, London 17, Singapore 16, Johor Bahru 12,
  Kuala Lumpur 10, others.
- Security-titled Alibaba Cloud roles: 26 China (Hangzhou 21, Beijing 13,
  Shanghai 5, plus IDC sites) and 8 overseas (Sunnyvale 3, Hong Kong 1,
  Helsinki 1, Jakarta 1, Johor Bahru 1, Munich 1).
- Example `100046940001` (阿里云智能-技术服务工程师TAM-出海KA客户-杭州,
  Hangzhou only, 3+ years, bachelor) is found by "技术服务" / "TAM" on both
  hosts but is excluded by the location classifier.
- Collector output: before the split `official_alibaba` kept 14 roles
  (13 Shanghai, 1 Malaysia; 6 of them Alibaba Cloud). After it,
  `official_aliyun` keeps 150 (128 Shanghai, 22 Malaysia; 152 eligible, the
  cap cut two BD roles) and `official_alibaba` keeps 8 Shanghai group roles.

## Tencent / Tencent Cloud

- Search:
  `GET https://careers.tencent.com/tencentcareer/api/post/Query`
- Detail:
  `GET https://careers.tencent.com/tencentcareer/api/post/ByPostId`
- Shanghai filter: `cityId=3`.
- Identity: `PostId`.
- Cloud hints: `ProductName=腾讯云` and/or `BGName=CSIG`.
- Polling: bounded pagination every 6 hours in V2.
- Live connector smoke test passed.

## Huawei / Huawei Cloud

- Portal: `https://career.huawei.com/cn/social-recruitment-job-list`
- API gateway:
  `https://apigw-dgg-b0.huawei.com/api/apig/channelhw`
- Shanghai body filter: `jobAddress=China\\Shanghai-Shanghai`.
- Identity: `advertisementId`.
- Cloud-family hint: `jobFamilyCodeList=["J23"]`.
- Limitation: gateway headers and request context are implementation details.
- Live connector smoke test passed after applying the complete gateway request
  header context.

## Xiaomi

- Portal: `https://career.mi.com/jobs`
- ATS: `https://xiaomi.jobs.f.mioffice.cn`
- Search:
  `POST /api/v1/search/job/posts`
- Shanghai code: `CT_125`.
- Identity: post ID.
- List rows contain full descriptions and requirements.
- WAF can intermittently return 405; use browser-like headers, low concurrency,
  and normal interval scheduling.
- Live connector smoke test passed.

## ByteDance

- Portal: `https://jobs.bytedance.com/experienced/position`
- Search:
  `POST https://jobs.bytedance.com/api/v1/search/job/posts`
- Shanghai code: `CT_125`.
- Social recruitment ID: `101`.
- Required headers include `portal-channel=society`,
  `website-path=society`, and `portal-platform=pc`.
- Identity: post ID.
- WAF can intermittently return 405; use low concurrency and bounded retries.
- Live connector smoke test passed.
