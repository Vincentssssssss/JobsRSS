# JobsRSS v2.2.4

## Release Focus

A redesigned filter panel. v2.2.3 had ten fields of different widths in a
wrapping grid, so the panel was tall and related controls ended up far
apart. The panel now has one row of inputs, one row of one-click chips, a
collapsible **More filters** section and a summary of what is applied.

Changes since v2.2.3: 3 commits. Frontend only; no API or schema change.
Default filters are unchanged (AI filter on at 60, fetch limit 500).

## Highlights

### Layout

- **Row 1:** search, location and sort. The sort labels are now
  **Sort: Newest posted** and **Sort: AI score ↓**, so the row needs no
  field labels. The help text moved to tooltips.
- **Row 2:** chips.
  - **AI:** `≥ 80`, `≥ 70`, `≥ 60` (default), `Any fit`, `Off`. This
    replaces the separate AI Precision Mode switch and AI Score select.
    `Any fit` keeps every strong or possible fit at any score; `Off` turns
    the AI filter off.
  - **Mine:** `All`, `★ Favorites`, `Applied`, `Not applied`,
    `Not viewed`. Favorites and Applied show how many jobs you have marked,
    and the counts update when you mark a job.
- **More filters** opens Source, Target Region, Rule Score and Fetch Limit.
  A badge on the button counts how many of them are set, so a filter is not
  hidden while the section is closed. Rule Score only applies with the AI
  filter off, so it is greyed out otherwise.
- **Summary row:** the number of matching jobs, then one tag for each
  applied filter, for example `AI: ≥ 80 ×` or `Source: amazon_aws ×`. Click
  a tag to remove that filter. **Clear all** appears with two or more tags
  and resets everything except the sort.
- In the Favorites and Applied views the AI chips are disabled, and the
  summary says that closed jobs are included and score filters are ignored.
  This was already how those views worked.

### Empty results

- "No jobs match these filters." now has a button that fixes it: **Turn the
  AI filter off** when the AI filter is on, otherwise **Clear all filters**.

### Small screens

- Below 760 px the search box takes the full width and location and sort
  share the next row. Chips wrap, and More filters stacks one field per row
  at phone width.

## Upgrade

```bash
cd ~/JobsRSS
git pull
docker compose up -d --force-recreate --no-build api worker frontend
scripts/smoke_test.sh
```

Wait about a minute for the dashboard to build, then reload with
Cmd+Shift+R. Your saved sort order is kept.

## Test Report

Runs were on 2026-11-05 on a test VM with live access to every career
site. The LLM rerank was off; AI scores were written into the test database
for about 980 collected jobs (one in seven left unscored) so the AI chips
had something to filter.

| Area | Commit | What ran | Result |
|---|---|---|---|
| Unit and integration tests | final | `pytest backend/tests` | 317 passed |
| Frontend typecheck | final | `npx tsc --noEmit` | passed |
| Filter behaviour | `7214d23` | Browser run at 1440 px (Asia/Shanghai): each AI chip, More filters, tag removal, Clear all, location, favoriting a job, the Favorites view, a search with no results | All passed. Default request is `min_llm_score=60` with strong and possible fits (495 jobs). `≥ 80` returned only cards scored 80 or more. `Off` dropped the AI parameters (1,002 jobs). The badge counted 2 with a source and a rule score set, and 1 once the AI filter was back on. The Favorites count went up when a job was favorited |
| Layout | `7214d23` | Same run at 1440, 1100, 1024, 900, 760, 700 and 390 px | No horizontal scrolling. The filter panel is 135 px tall at 1440 px with More filters closed |
| Smoke test | final | `scripts/smoke_test.sh` | SMOKE_RESULT |

The first browser run found that the More filters dropdowns clipped their
text and that one overlapped the next column at 900 px. `7214d23` fixes
both.

## Known Issues

- Known issues from v2.2.3 still apply.
