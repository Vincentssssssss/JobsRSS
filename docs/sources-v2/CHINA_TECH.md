# V2 China Technology Source Assessment

Assessment date: 2026-08-21

No documented public careers API, RSS/Atom feed, or useful jobs sitemap was
found for these companies. The selected sources are undocumented first-party
web APIs and must be monitored for schema changes.

## Alibaba / Alibaba Cloud

- Official portal: `https://campus-talent.alibaba.com/campus/position`
- Method: first-party JSON with XSRF token.
- Scope currently verified: campus/intern recruitment.
- Shanghai filter: `regions: "上海"`.
- Alibaba Cloud requires dynamically discovered leaf department codes.
- Limitation: no verified equivalent social-hire API; batches and department
  codes change by campaign.
- Live campus connector smoke test passed with Shanghai multi-location roles.

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
