# Storyforge API

A FastAPI layer over the GitHub Actions story pipelines, so a frontend can start runs, follow them live and read the results. The API never runs models. It dispatches the existing workflows with the caller's GitHub token and reads the artifacts those workflows upload.

```
browser (web/ or your frontend)
   │  Authorization: Bearer <GitHub token>
   ▼
Storyforge API (storyforge/api)          ── demo token ──▶ bundled sample runs
   │  same token, per request
   ▼
GitHub REST API ──▶ workflow_dispatch ──▶ Actions runs ──▶ artifacts
```

## Run it locally

```bash
python -m pip install -e '.[api]'
uvicorn storyforge.api.app:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Playground frontend: `python -m http.server 8080 -d web`, then open http://localhost:8080 and click **Use demo data**.

## Authentication

Every route except `/health`, `/modes` and `/requests*` needs:

```
Authorization: Bearer <GitHub token>
```

- Users bring their own token. The server uses it for that one request and does not store or log it.
- Fine-grained token: repository access to the Storyforge repo with **Actions: read and write** (and Metadata: read). Classic token: the `repo` scope.
- `Bearer demo` serves bundled sample data with no GitHub calls (disable with `STORYFORGE_ALLOW_DEMO=0`).
- `GET /api/v1/auth/check` returns `{login, repo, can_dispatch, demo}`. Use it as the login check.

Serve the API over HTTPS anywhere other than localhost, since tokens pass through it.

## Modes

`GET /api/v1/modes` returns each mode with every input it accepts (name, type, options, default, description). Build start forms from that response rather than hard-coding fields.

| Mode | Workflow | Starts from | What it does |
|---|---|---|---|
| `sequential` | `living-universe-pipeline.yml` | a story brief | Writes scenes one at a time; each is reviewed, repaired and committed to canon before the next. |
| `parallel` | `planned-parallel.yml` | a story brief | Plans every scene first, then writes and checks all scenes at once on separate runners. |
| `recovery` | `resume-story.yml` or a fresh sequential run | a failed sequential run | Continues from the first unfinished scene, keeping approved scenes and saved drafts. |

Recovery has two strategies:

- `fresh` (default): starts a **new** sequential run with `fresh_run=<failed run>`. The new run imports the approved prefix and rechecks unfinished drafts. The response's `run_id` is the new run.
- `rerun`: dispatches `resume-story.yml`, which re-executes the failed job **inside the original run**. The response's `tracks_run_id` is the original run; follow that one (its `attempt` goes up).

## Endpoints

All paths are under `/api/v1`.

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/health` | no | `{ok, version, repo, ref, demo_available}` |
| GET | `/modes` | no | `Mode[]` |
| GET | `/requests` | no | `RequestSummary[]`: briefs in `examples/` |
| GET | `/requests/{id}` | no | The full brief JSON |
| POST | `/requests/validate` | no | `{valid, error, normalized}` for a brief in the body |
| GET | `/auth/check` | yes | `AuthCheck` |
| GET | `/runs?mode=&status=&tag=&limit=` | yes | `{runs: RunSummary[]}` newest first |
| POST | `/runs` | yes | `StartedRun` (202) |
| GET | `/runs/{id}` | yes | `RunDetail`: status, jobs, progress, `recoverable`, warnings |
| GET | `/runs/{id}/events` | yes | Server-sent events stream of `RunDetail` |
| POST | `/runs/{id}/recover` | yes | `StartedRun` (202) |
| POST | `/runs/{id}/cancel` | yes | `{cancel_requested: true}` (202) |
| GET | `/runs/{id}/story` | yes | `Story`: full text and per-scene status |
| GET | `/runs/{id}/scenes/{scene_id}` | yes | `Scene`: prose and raw reviews |
| GET | `/runs/{id}/canon` | yes | `Canon`: committed memories (sequential only) |
| GET | `/runs/{id}/artifacts` | yes | `{artifacts: Artifact[]}` |
| GET | `/runs/{id}/artifacts/{name}` | yes | The artifact zip |

Full schemas: http://localhost:8000/docs, or the committed [web/openapi.json](../web/openapi.json) for client generation.

### Start a run

```http
POST /api/v1/runs
Authorization: Bearer ghp_...
Content-Type: application/json

{
  "mode": "sequential",
  "request_file": "living-scale-practice",
  "backend": "fixture",
  "inputs": { "profile": "fast", "scene_limit": "2" }
}
```

```json
{ "mode": "sequential", "workflow": "living-universe-pipeline.yml", "run_id": 40123456789,
  "tracking_tag": "api-1a2b3c4d", "tracks_run_id": null,
  "html_url": "https://github.com/TanishC4444/storyforge-gh-test/actions/runs/40123456789" }
```

- `backend: "fixture"` checks the plumbing with labelled synthetic prose in a few minutes. `"live"` runs real models and can take hours.
- `inputs` accepts only the inputs `GET /modes` lists for that mode. Unknown inputs or invalid choices return 422.
- `run_id` can be `null` if GitHub has not listed the run yet. Poll `GET /runs?tag=<tracking_tag>` until it appears.
- Briefs must already exist in `examples/` on the dispatched branch, because the workflows read them from the checkout.

### Recover a failed run

```http
POST /api/v1/runs/40109187765/recover
{ "strategy": "fresh", "backend": "live", "inputs": { "scene_limit": "2" } }
```

Only failed sequential runs can be recovered (409 otherwise). `RunDetail.recoverable` tells the UI when to show the button.

### Run status

Every run uses one status vocabulary, whatever GitHub reports:

| `status` | Meaning |
|---|---|
| `queued` | Waiting for a runner |
| `running` | In progress |
| `succeeded` | Finished; every scene passed review |
| `succeeded_with_warnings` | Finished, but some scenes are provisional (`warnings` lists them) |
| `failed` | Stopped; check `recoverable` |
| `cancelled` | Cancelled |

`progress` gives `jobs_done / jobs_total` for a progress bar and `accepted_scenes / total_scenes` when known. `total_scenes` counts every scene in the brief, so a run started with a smaller `scene_limit` finishes with fewer accepted scenes than the total. For sequential runs it is known once the run finishes.

A failed sequential run also reports `resume_scene`, the first unfinished scene that recovery would restart from.

### Following a run live

`GET /runs/{id}/events` streams `text/event-stream`:

```
event: run
data: {...RunDetail...}

event: end
data: {}
```

A `run` event is sent whenever the run changes (the server polls GitHub every 15 s). `end` arrives when the run finishes. Streams close after 30 minutes; reconnect if the run is still going. Browsers cannot send headers with `EventSource`, so read the stream with `fetch`. `web/js/api.js` has `watchRun(id, {onRun, onEnd, onError})`, which does this.

### Errors

Errors are `{"detail": "message"}` with:

| Code | When |
|---|---|
| 401 | Missing or bad token |
| 403 | Token lacks permission on the repo |
| 404 | Unknown run, brief or scene, or the artifact is not uploaded yet or has expired |
| 409 | Action does not fit the run (recovering a successful run, canon for a parallel run) |
| 422 | Invalid body or inputs |
| 502 | GitHub could not be reached or failed |

Artifacts expire (7 to 30 days depending on the workflow), so old runs can return 404 for content.

## Frontend playground (`web/`)

A dependency-free page for trying the API and seeing how a frontend could look:

- `web/js/api.js`: the reusable client (`StoryforgeClient`). Import it from any framework.
- `web/js/app.js`, `web/index.html`, `web/styles.css`: the playground UI. Edit or replace freely.
- `web/console.html`: the **API console**. It has one button per endpoint, with inputs for every parameter, and shows the raw response, HTTP status and timing plus a call log. Use it to check any backend feature before building UI for it. Buttons outlined in red start or change real runs.

The API URL defaults to `http://localhost:8000`. Change it in the connection panel or with `?api=https://your-api.example`.

### GitHub Pages

`.github/workflows/pages.yml` deploys `web/` on every push to `main` that touches `web/`. A repo admin must enable it once: **Settings → Pages → Build and deployment → Source: GitHub Actions**. The site is then at https://tanishc4444.github.io/storyforge-gh-test/.

The hosted page still needs a running API:

- **Local API:** Chrome and Firefox allow a GitHub Pages page to call `http://localhost:8000` (Chrome may ask for local network permission). Safari blocks it, so use the local playground there.
- **Hosted API:** deploy the API anywhere that runs Python (Render, Fly.io, a VM) and add the page origin to `STORYFORGE_CORS_ORIGINS`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `STORYFORGE_REPO` | `TanishC4444/storyforge-gh-test` | Repo whose workflows are dispatched and read |
| `STORYFORGE_REF` | `main` | Branch to dispatch on |
| `STORYFORGE_ALLOW_DEMO` | `1` | Accept the `demo` token |
| `STORYFORGE_CORS_ORIGINS` | localhost:5173, localhost:8080, 127.0.0.1:8080, tanishc4444.github.io | Comma-separated allowed browser origins |
| `STORYFORGE_CACHE_DIR` | `runs/api-cache` | Downloaded artifact zips, keyed by artifact ID |
| `STORYFORGE_POLL_SECONDS` | `15` | GitHub polling interval for event streams |

## Changing the API

The code is split so most changes touch one file:

| To change | Edit |
|---|---|
| Response or request fields | `storyforge/api/schemas.py`. Add fields; avoid renaming or removing them. |
| Mode inputs, or a new mode | `storyforge/api/modes.py` |
| How story, scene or canon data is read from artifacts | `storyforge/api/artifacts.py` |
| GitHub calls | `storyforge/api/github.py` and `GitHubBackend` in `service.py` |
| Sample data for demo mode | `storyforge/api/demo.py` and `demo_data/` |
| Routes | `storyforge/api/app.py` |

After changing the API:

```bash
python -m unittest tests.test_api -v
python -m scripts.export_openapi   # keeps web/openapi.json current
```

`tests/test_api.py` fails when a workflow's inputs drift from `modes.py`, or when `web/openapi.json` is stale.

## Not built yet

- **Custom briefs.** Runs start only from briefs already committed in `examples/`. A future `POST /requests` could commit a validated brief through the GitHub Contents API.
- **Multiple users and accounts.** The API trusts whoever holds a working token and keeps no user records.
- **Rate limits.** Each `GET /runs/{id}` costs 2 to 3 GitHub API calls. A personal token allows 5,000 per hour.

## Validation and regression checks

`GET /requests` includes `supported_modes` for each brief. The playground offers
only compatible briefs and disables scene limits beyond the authored scene count.
The API rejects incompatible mode/brief combinations before dispatch, invalid run
IDs and status filters, unknown launch/recovery fields, and invalid continuation
IDs. An omitted sequential scene limit is bounded by the selected brief. Fresh
recovery inherits the saved episode length and original backend when omitted;
it rejects a limit that would skip the failure or an explicit backend mismatch.

The story endpoint and collector preserve approved scenes imported during fresh
recovery, even when those scenes have no new preview artifacts. Saved unfinished
scenes remain readable with their provisional status; they do not become canon.
Corrupt upstream artifacts return a gateway error, and corrupt zip cache entries
are removed so a later fetch can recover.

Both HTML pages use the same API client. Requests time out with an actionable
message; timed-out POST requests are never automatically retried. Event parsing
supports CRLF, split UTF-8 and multiline data, releases readers on exit, and
reports a dropped stream rather than treating it as completion. Refresh the run
view to reconnect after an interrupted stream. Switching views or forgetting a
token invalidates stale asynchronous callbacks.

Run backend and client regressions with:

```sh
python -m pip install -e '.[api,test]'
python -m unittest discover -s tests -v
node --test tests/test_web_client.mjs
```

Demo launches, cancellation and recovery are simulated. They test the HTTP/UI
contract without consuming inference quota; completed real-run artifacts should
also be backtested through the API before a release. Local concurrent-request
measurements are not a production capacity guarantee.
