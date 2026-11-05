# JobsRSS v2.2.2

## Release Focus

A denser job list that opens into a list-plus-details workspace, and local
updates that no longer depend on Docker Hub. Before this release the
dashboard was baked into its image, so every dashboard change needed
`docker compose build frontend`. That build pulls `node:22-alpine` from Docker
Hub. Where Docker Hub is unreachable the build failed, and the old dashboard
kept running with no sign that anything was wrong.

Changes since v2.2.1: 4 commits. Patch release; no schema change.

## Highlights

### Job list and details

- Cards are two lines: title, company and score on the first, and
  place · source · posted date · target region on the second. Favorite,
  Applied and Open are in the card footer. About twice as many jobs fit on a
  screen.
- Clicking a job splits the page into a compact list and a details pane
  pinned beside it (1024 px and wider). On narrower windows the details open
  as a dialog over the list.
- In the details pane, J and K step to the next and previous job, and Esc
  closes it. The pane shows the card's header right away and fills in the
  description when it loads; LLM reasons come before the description.
- Fixed horizontal scrolling below about 900 px: long one-line text widened
  the page instead of being cut off.

### Updating without Docker Hub

- `docker-compose.yml` now mounts the dashboard code (`frontend/app`,
  `package.json`, `next.config.ts`) into the `frontend` container, which runs
  `npm run build` when it starts. Like the api and worker, the dashboard now
  runs the checked-out code, and an update is `git pull` plus a recreate.
  The existing image is reused for node and `node_modules`. A rebuild is
  needed only when `package-lock.json` or the Dockerfile changes.
- The dashboard starts about a minute after a recreate while it builds.

### Version checks

- The title shows the dashboard version (`v2.2.2`).
- A yellow warning appears when the dashboard is older than the API, with the
  command that fixes it.
- `scripts/smoke_test.sh` adds two checks: the frontend container has the
  checked-out dashboard code, and the page serves this release's version.
  It also waits up to two minutes for the dashboard to finish building.

## Upgrade

From v2.2.1 or earlier. No `docker compose build` is needed, so this works
even when Docker Hub is unreachable:

```bash
cd ~/JobsRSS
git pull
docker compose up -d --force-recreate --no-build api worker frontend
scripts/smoke_test.sh
```

Reload the dashboard with Cmd+Shift+R. The title then reads
`JobsRSS Intelligence v2.2.2`.

## Test Report

All runs were on 2026-11-04 on a test VM.

| Area | Commit | What ran | Result |
|---|---|---|---|
| Unit and integration tests | `196a6d4` | `pytest backend/tests` | 303 passed |
| Frontend typecheck | `196a6d4` | `npx tsc --noEmit` | passed |
| Layout | `697d20d` | Browser run at 1440, 1100, 1024, 1000, 900 and 700 px: list view, open a job, J/K, Esc, dialog on narrow windows | all steps passed; no horizontal scrolling at any width |
| Stale dashboard detection | `e22cf0d` | Dashboard image from v2.2.1 (`e19e603`) against the v2.2.2 API | Yellow warning shown; smoke test failed only the version check, with the fix command. After the update: passed |
| Update with Docker Hub blocked | `196a6d4` | Dashboard image built from v2.2.1; Docker Hub and the npm registry blocked (`docker pull node:22-alpine` fails); then `git pull` and the upgrade commands above | Dashboard rebuilt in the container and served v2.2.2; smoke test 50 passed, 0 failed, 1 warning (LLM off) |

Found and fixed during testing:

- Horizontal scrolling caused by one-line text in grid columns.
- On narrow windows the dialog's backdrop did not dim the list, and card text
  showed through the pane (a Chromium issue with translucent fixed layers).
  The pane is now opaque.

## Known Issues

- A dashboard with uncommitted local edits under `frontend/app` is built as
  is; a build error keeps the frontend container restarting. Check
  `docker compose logs frontend`.
- Known issues from v2.2.1 still apply.
