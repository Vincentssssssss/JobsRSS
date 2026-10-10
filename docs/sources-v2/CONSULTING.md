# V2 Consulting Source Assessment

Assessment date: 2026-09-04

MBB and Big Four were added to the official source registry so they appear
in the portal source list. Collectors are enabled only where a stable
first-party inventory API was verified.

## Boston Consulting Group / BCG

- Official search: `https://careers.bcg.com/global/en/search-results`
- ATS: Phenom widgets (`POST https://careers.bcg.com/widgets`).
- Shanghai filter: `selected_fields.city=["Shanghai"]`.
- Identity: `jobSeqNo`.
- Detail payload includes full HTML `description` and apply URL.
- Status: operational (`json`).

## Deloitte / 德勤

- Official China experienced-hire portal:
  `https://ehjobs.deloitte.com.cn/SU649e304a6a9f0ef690533e9a/pb/social.html`
- ATS: HotJob on a Deloitte vanity host, not `wecruit.hotjob.cn`.
- Tenant: `SU649e304a6a9f0ef690533e9a`.
- List/detail JSON reuse the existing HotJob contract.
- Location is filtered locally; explicit non-Shanghai cities are excluded.
- Status: operational (`json`).

## KPMG / 毕马威

- Official China social board:
  `https://app.mokahr.com/social-recruitment/kpmg/68240`
- ATS: Moka encrypted JSON (`orgId=kpmg`, `siteId=68240`).
- Some Shanghai rows only expose `cityId` (`310xxx`) plus a street address,
  so the Moka location parser maps `310*` city IDs to `上海`.
- Status: operational (`encrypted_json`).

## McKinsey & Company

- Official search: `https://www.mckinsey.com/careers/search-jobs`
- Apply portal: `https://jobs.mckinsey.com/`.
- No stable public list/detail JSON contract was verified.
- Status: registered, `assessment_pending`.

## Bain & Company

- Official careers: `https://www.bain.com/careers/find-a-role/`
- Apply portal: `https://careers.bain.com/`.
- No stable public job inventory API was verified.
- Status: registered, `assessment_pending`.

## PwC / 普华永道

- Official experienced-hire page:
  `https://www.pwccn.com/zh/careers/experienced-jobs.html`
- Campus Moka board exists, but no verified experienced-hire inventory API.
- Status: registered, `assessment_pending`.

## EY / 安永

- Official China careers: `https://www.ey.com/en_cn/careers`
- Global apply portal is SuccessFactors-backed (`careers.ey.com`).
- No stable public experienced-hire inventory API was verified.
- Status: registered, `assessment_pending`.
