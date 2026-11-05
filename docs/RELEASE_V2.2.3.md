# JobsRSS v2.2.3

## Release Focus

Show when each job was posted, and sort the list by AI score. Getting the
dates right meant fixing three sources whose dates were missing or wrong. It
also exposed a bug that cleared every job's AI score once, so each job was
scored twice.

Changes since v2.2.2: 9 commits. Patch release; no schema change.

## Highlights

### Posting dates

- Each card shows the date and age under the score, for example
  `Posted Nov 2 · 3d ago`. The details pane shows the full date.
- The label says what the date is. **Posted** is the source's publish
  date. **Updated** marks Tencent and Huawei, which only give the date a
  posting was last updated. **First seen** (italic) marks a listing with no
  date and shows when JobsRSS first collected it.
- Ages count calendar days in your time zone, so a job dated Nov 3 reads
  "2d ago" all day on Nov 5.

### Sorting

- A **Sort By** filter: **Newest posted first** (the default) or
  **AI score, highest first**. The browser remembers the choice.
- AI score: equal scores go newest first. Jobs without an AI score come last,
  by rule score.
- Newest first uses the first-seen date for jobs without a posting date.
  Before, those jobs sorted as NULL, which Postgres puts at the top of a
  descending sort.
- API: `GET /jobs?sort=newest|ai_score`; any other value returns 422.
- RSS feeds now list newest first. feedgen prepends entries by default, so
  every feed was in reverse order.

### Date fixes

- **Google** (190 active jobs) had no dates. Its pages have no schema.org
  date, but the embedded job record has create, update and publish times. The
  collector now reads the publish time, which is what Google's own date sort
  uses.
- **Tencent** (150 jobs) had no dates. It writes `2026年11月05日`, which the
  date parser did not read. `2026/11/05` and `2026.11.05` are also read now.
- **Chinese portals** (Moka: KPMG, GSK, WuXi Biologics, ANTA; Beisen:
  WuXi AppTec, CTTQ, Innovent, Fosun; HotJob: Deloitte, Simcere, Yunnan
  Baiyao) send Beijing time without an offset, and it was read as UTC.
  Times were 8 hours late: KPMG jobs posted that morning were dated in the
  future and sorted above everything else, and evening postings were dated
  the next day. Collectors for Chinese portals now read such times as
  Beijing time.

### AI scores are kept

- A job's AI score was cleared whenever its stored content hash changed. A
  new row stores the collector's hash, and later sightings compare a hash
  built differently, so **every job's score was cleared on its second
  sighting** and the job was scored again. A date change cleared it too, so
  this release's date fixes would have cleared about 1,500 scores.
- Scores now reset only when something the LLM reads changes: title,
  company, location or description.

### Smoke test

- Checks that both sort orders return correctly ordered lists and that an
  unknown sort is rejected.

## Upgrade

```bash
cd ~/JobsRSS
git pull
docker compose up -d --force-recreate --no-build api worker frontend
scripts/smoke_test.sh
```

Wait about a minute for the dashboard to build, then reload with
Cmd+Shift+R. Google and Tencent jobs get their dates, and Chinese portals
their corrected times, on the next run of each collector. Recreating the
worker starts that run, and it finishes in about 12 minutes. AI scores are
kept.

## Test Report

Runs were on 2026-11-05 on a test VM with live access to every career
site. The LLM rerank was off; AI scores were written into the test database
to exercise sorting and score retention.

| Area | Commit | What ran | Result |
|---|---|---|---|
| Unit and integration tests | final | `pytest backend/tests` | 317 passed (303 in v2.2.2) |
| Frontend typecheck | final | `npx tsc --noEmit` | passed |
| Dates before the fix | `291d22a` | Live run of all 23 official collectors | 1,967 active jobs; Google (205) and Tencent (150) had no date; 16 KPMG jobs were dated 5 to 7 hours in the future |
| Dates after the fix | `5f9e7dd` | Recreated api and worker on the same database; full collection cycle | 1,957 active jobs, all dated, none in the future. Chinese portal times fall in Beijing working hours. Google closed 15 rows older than 60 days |
| AI score retention | `da88c74` | Scores written for 1,677 jobs, then a full collection cycle | 1,677 kept. The cycle before the fix cleared all 150 Tencent scores and most Midea, WuXi Biologics and ANTA scores |
| Sorting | `7650593` | `GET /jobs` on Postgres with `sort=newest`, `ai_score`, `bogus` | Correct order; NULL dates not first; 422 for `bogus`; RSS newest first |
| Dashboard | `9a06e3a` | Browser run at 1440 px (Asia/Shanghai): default sort, AI score sort, reload, open a job, Tencent, Google and an undated job; widths 1100 to 390 px | All passed; the choice survives a reload and the first request already uses it; no horizontal scrolling |
| Smoke test | final | `scripts/smoke_test.sh` | 53 passed, 0 failed, 1 warning (LLM off) |

## Known Issues

- Tencent and Huawei give only a last-updated date. Moka portals (KPMG, for
  example) re-publish postings, and the publish date moves with each
  re-publish.
- Liepin and 51job dates come from card text such as `3天前`. They were not
  tested here (no login on the test machine). Cards without a date show
  **First seen**.
- Rows are corrected when their collector next runs, not at startup.
- Known issues from v2.2.2 still apply.
