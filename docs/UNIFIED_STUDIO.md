# Unified FastAPI studio

The repository's HTML writing frontend, production planner, image studio, audio
services and workflow explorer now run under one FastAPI origin.

```powershell
python -m pip install -e ".[api]"
python -m storyforge.studio
```

Open **http://127.0.0.1:8000/**. The installed command is `storyforge-studio`.
Use `--port` to change the port. Optional `--workspace` selects the repository /
workspace containing story output folders; default is this checkout. The old
standalone development servers remain available, but are not required by the
unified app. Start this local studio on loopback; its workspace endpoints reject
nonlocal hosts/clients. It is not a multi-user hosted service.

## Workspaces

| Page | Function |
| --- | --- |
| `/` | Project creation/import, workspace links, recent background jobs |
| `/writing` | Existing Sequential, Parallel and Recovery frontend and workflow API |
| `/ideas` | Muse Glimmer ideation, writing, critique, manual revision and bounded revision loops |
| `/images` | Existing Vultr image studio, editable visual prompts, gallery, scouting handoff |
| `/music` | Vultr scores/songs, progressive playback, save/cancel, and explicit local ambience |
| `/production` | Existing schedules, budgets, scouting, legal/logistical research and calendar exports/sync |
| `/workflows` | All workflows, input schemas, source/job graphs, historical runs, job logs and artifacts |
| `/outputs` | Per-project file library, text/JSON/image/audio previews and downloads |
| `/connections` | Provider credentials for this server session, without writing secrets to disk |
| `/testing` | Interactive console generated from every documented OpenAPI operation |
| `/docs` | FastAPI Swagger documentation and endpoint execution |
| `/console` | Original writing API test console |

## Projects and outputs

The app discovers story run folders under `outputs/` and `runs/`. The project
selector is shared by all studio tools; it uses an HTTP-only cookie and never
accepts arbitrary filesystem paths. A new text/Markdown upload or JSON story brief
creates a separate project under `runs/studio-projects/`. New projects do not
replace accepted manuscripts or canon. Image, music and production services use
the current project folder. Jobs capture their project at submission time, so
switching projects does not move a running job's output.

The file library exposes bounded supported file types from registered projects,
with traversal/symlink checks and no executable HTML previews. Secret/config files
and provider-budget directories are excluded. Creative steps, media prompts,
provider model/usage and production evidence are retained alongside outputs.

Local jobs are recorded under `runs/studio-jobs/`, execute in a two-worker pool,
and allow at most four active submissions. A restart marks unfinished jobs as
interrupted rather than pretending completion or automatically charging a retry.
Recent job lists are bounded; the actual saved output files remain available.

## Writing and the idea/revision loop

The original workflow API and its three modes are preserved. Use the writing
frontend with `demo` to explore bundled examples, a GitHub token for real runners,
or **Use server GitHub connection** when a server fallback token is configured.
The complete separate-runner workflow graphs are unchanged.

The local creative workspace offers independent Ideas, Draft, Review and Revise
actions. It can include the current story or work solely from the supplied brief
and text. The loop starts from supplied text or generates a candidate, then
critiques and revises it for at most 1–3 review rounds. Maximum provider calls are
one initial generation plus two calls per round; it stops early when the reviewer
passes the candidate. If the final step is a revision, the last review applies to
the preceding candidate and the UI/record explicitly say it does not validate the
new final version. Every step and its usage is saved in `creative/`. An AI passing
review never commits canon. A result can be copied into the next manual revision
or adopted as a **new** media project.

Custom uploaded briefs are immediately usable by local creative/media/planning
features. Hosted runners require a full validated JSON brief committed to
`examples/` on their Git ref. The Home page includes an explicit publish action
using GitHub's Contents API (Contents write permission required). It does not
publish on import, silently overwrite existing briefs, or edit workflow files.
After publishing, dispatch a workflow whose `request_file` input accepts the new
name. Some older workflows restrict that input to a fixed choice list.

## All workflow and inference-runner history

The workflow catalog includes local YAML definitions and can merge the remote
GitHub catalog so newly added/older workflow families are not hidden behind the
three supported writing modes. The UI loads the remote catalog and uses the
selected Git ref's real schema before dispatch. Source/job graphs display declared
jobs and dependencies; actual expanded matrix jobs and steps are shown in run
history. The selected run's exact source revision can also be inspected.

History lists **all events/workflows**, with repository, workflow and pagination
controls. It is not limited to `workflow_dispatch`. Public metadata works without
a token; private repositories, artifact downloads, logs and write actions need
appropriate GitHub permissions. Set `STORYFORGE_GITHUB_TOKEN` as an optional
server-side fallback or supply a token per request. Tokens are never stored in
project/job records. The Connections page may set the fallback for this process.

`STORYFORGE_RUNNER_REPOS` is a comma-separated allowlist of additional repositories.
The default is `<main-repo-owner>/storyforge-inference-runner`; the UI also permits
setting additional owner/name pairs in Connections. Only configured repositories
can be accessed by the generic workflow browser. The main repository is set by
`STORYFORGE_REPO`. Existing client settings control GitHub API base URL and ref.
Metadata is cached briefly with credential-scoped cache keys. GitHub uses the
system certificate trust store with certificate/hostname verification enabled.

For any previous run you can inspect jobs/steps, retrieve job logs, browse artifact
file lists, preview individual text/JSON/image/audio files, download artifact ZIPs,
and import a selected readable manuscript as a new local project. Re-run, re-run
failed jobs and cancel are separate explicit buttons. No workflow is dispatched
when the catalog or a historical run is opened. Recovery's two strategies remain
available in the original writing interface.

Artifacts expire according to GitHub retention. The app labels expired artifacts;
it cannot reconstruct expired remote data. Previously saved local outputs remain
readable. In-app ZIP download/inspection is limited to 64 MB compressed, 128 MB
uncompressed and 2,000 files; a single preview is limited to 4 MB. The run's GitHub
link remains available for larger downloads. Archives are never extracted to
arbitrary filesystem paths.

## Media and production

Existing generation code is called directly by FastAPI background jobs; there is
no HTTP proxy to the old 8765/8766 servers and no embedded iframe frontend.
Image and planning legacy route names are retained to keep their existing UIs
working. Generated image scouting links stay on this FastAPI origin.

Vultr music submission is an asynchronous provider job. Status polling stops on a
terminal state; audio controls retain their player during progress updates.
Progressive streams are proxied with the key on the server. Saved completed tracks
become ordinary local outputs. Score mode requests instrumental sections, but
Vultr's current model can still introduce vocals. Local ambience is an explicit,
separately labelled option. Cancel sends the provider cancellation request; a
stopped browser audio player does not cancel paid generation. There are no
automatic paid retries or provider substitutions.

The image studio uses the live provider catalog and records the actual image model
(e.g. MOSS-Image through Vultr, or the configured Meta Muse Image adapter when available). Muse Glimmer writes visual prompts and production recommendations.
SerpAPI retains its per-plan/daily limits, cache and ordered key cooldown/failover.
See `IMAGE_STUDIO.md` and `PRODUCTION_PLANNING.md` for model limits and planning
assumptions. Google OAuth uses this server's `/google/callback` URL; register the
port actually used. Credentials and user consent remain required for direct
Calendar sync. ICS export needs no Google account connection.

## Connections and test scope

Environment names remain documented in `.env.example`; the app does not load
`.env` automatically. Credentials entered in Connections exist only in process
memory and are never echoed back. Blank fields preserve current values. Configure
Google OAuth separately; a Vultr or SerpAPI key cannot authorize a personal calendar.

The test console includes every documented GET/POST endpoint from `/openapi.json`.
Path and query inputs and JSON request bodies are editable. It can render JSON,
text, images/audio and event streams; Stop reading cancels an in-browser stream.
Stopping response reading does not cancel a running server/provider job. Swagger
provides the complementary schema-based test interface. Test actions with external
side effects execute only on an explicit button press.

```powershell
python -m unittest tests.test_unified_studio tests.test_api tests.test_image_studio tests.test_production tests.test_soundtracks -v
python -m scripts.export_openapi
```

The integration suite uses mocked providers for expensive/writing operations and
GitHub mutations, checks project isolation and traversal, validates the job adapters,
local audio and Vultr status handling, enforces workflow schemas, verifies archive
limits and artifact-to-project imports, and tests review/revision call bounds.
Live checks must be reported separately; mock coverage is not a claim that every
external provider or historical workflow has been executed.
