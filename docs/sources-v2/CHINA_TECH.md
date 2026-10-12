# V2 China Technology Source Assessment

Assessment date: 2026-08-21

No documented public careers API, RSS/Atom feed, or useful jobs sitemap was
found for these companies. The selected sources are undocumented first-party
web APIs and must be monitored for schema changes.

## Alibaba / Alibaba Cloud

- Official portal: `https://talent.alibaba.com/off-campus/position-list?lang=zh`
  (social recruitment; the campus portal is no longer collected).
- Search: `POST https://talent.alibaba.com/position/search` with
  `{"channel", "language", "key", "pageIndex", "pageSize"}` (`pageSize` 100 works).
- Channels: `group_official_site` (`language: zh`, China) and
  `group_overseas_official_site` (`language: en`, overseas incl. Malaysia).
- XSRF: `GET` the portal page (answers 302) to receive the `XSRF-TOKEN`
  cookie, then send it as `X-XSRF-TOKEN` with a portal `Referer`.
- Rows include `description`, `requirement`, `workLocations` (city names),
  `experience.from`, `publishTime`; no detail call is needed.
- Shanghai can be filtered server-side with `regions: "310100"`, but the
  collector keyword-searches "安全" / "security" and filters `workLocations`
  client-side because most roles list several cities.
- Live smoke test (2026-10-09): 116 "安全" roles in China (13 in Shanghai) and
  8 overseas "security" roles (1 in Johor Bahru).

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
