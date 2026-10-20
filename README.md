# Storyforge GH Test

A public experimental testbed for developing fiction with literary retrieval, fresh GH-AI runners, distinct-writing editing, story-quality review, and file-backed memory. No Gemini and no UI.

**Status:** deterministic three-chapter coordination and failure/resume tests pass locally. The fixture backend does not generate fiction or measure model quality. The live adapter is implemented but has not been end-to-end validated on three chapters in this repo. Treat model reviews as fallible.

## How it works

One local coordinator owns state. Every uncached role call dispatches a **fresh GitHub runner job** through the included GH-INFERENCE source snapshot. Each receives only its explicit packet; there is no shared chat history.

1. Retrieve a few literary mechanisms and master-guide sections, then run a dedicated initial-prompt refinement stage. Refinement preserves explicit choices and labels proposals before chapter planning.
2. Story Architect creates a structured plan.
3. Participating characters each propose one outward action using scoped knowledge.
4. Director turns the proposals into a bounded scene direction.
5. Writer drafts complete prose.
6. Distinct-writing editor improves voice, detail, subtext, and rhythm while preserving events.
7. Story Quality checks the revised scene and, where needed, requests one bounded repair.
8. Memory extractor proposes evidence-linked updates; a separate fresh reviewer checks the proposed memory.
9. At chapter boundaries, a fresh reviewer checks the full chapter.
10. Only an accepted scene and its reviewed memory become the next atomic state version. Export assembles three chapter files and story.txt.

The character round is deliberately bounded. It is not an open-ended group chat. The director can decline a proposal; character proposals do not become canon simply because an agent generated them.

Fresh workers reset inference state; they do not increase model context capacity. Every worker still has its configured context window. Relevant memory is selected explicitly. The prototype retains all accepted prose and memory on disk but currently uses a recent-memory selection policy bounded by both item count and 4,500 characters; it can miss important old facts. It does not claim perfect long-form continuity.

## Quick start: no credentials or model downloads

Python 3.11+ with SQLite FTS5 is recommended.

```bash
python -m storyforge.cli --request examples/harbor.json --out runs/fixture --backend fixture
python -m unittest discover -s tests -v
```

The fixture backend uses real current-corpus keyword retrieval and deterministic synthetic responses for the model stages. It writes nine short fixture scenes, three chapter files, and labelled test output. Fixture length checks are intentionally bypassed. These files prove coordination only, and must not be presented as a generated novel.

The example live target is three chapters × three scenes × 850 words, around 2,550 words per chapter. Each accepted live scene must pass the configured length range. Natural-language and model checks do not guarantee literary quality.

## Run actual inference

```bash
python -m venv .venv
# Activate the environment for your OS.
python -m pip install -e . ./vendor/gh-inference
# Set GH_AI_TOKEN in your shell; never put it in a request JSON.
python -m storyforge.cli --request examples/harbor.json --out runs/live --backend github --stop-after 1
python -m storyforge.cli --out runs/live --resume --backend github
```

Start with one live scene. A PAT must have the repository/workflow access required by GH-INFERENCE, including permission to create/update and dispatch its dedicated inference repository. Fine-grained token support depends on those operations and account policy. The ordinary automatic GITHUB_TOKEN is not a substitute for cross-repository setup permissions. See the included library README for token and worker setup.

The GH-AI library prepares a separate inference repository named by runner_repo (default storyforge-inference-runner). Run only one coordinator per inference repo at first: different coordinators can otherwise race workflow updates. A timeout can leave a remote job still running; inspect last-job.json and its Actions run before resuming. The coordinator does not cancel timed-out remote work.

The request defaults to automatic plan approval only in the provided example. To inspect the plan before any scene starts, set auto_approve_plan to false, run once, then resume with --approve-plan. Approval accepts the generated plan as development direction; it does not turn planned events into accepted prose.

Do not change the request or accepted state in-place during a run. Start a new run folder for changed premises or accepted early scenes. Dependency-based surgical revisions are not implemented yet. If a pending stage repeatedly fails, inspect its work and calls; a new run with corrected inputs is the safe recovery path. Resume is for the same request and backend. It reuses completed calls and accepted scenes.

## Model routing

| Profile | Planning, character, direction, review, memory | Writer | Distinct-writing editor |
|---|---|---|---|
| balanced (default) | gemma-4-12b | gemma-4-12b | gemma-4-12b |
| expressive | gemma-4-12b | glitter-12b | gemma-4-12b |
| small | qwen3b | qwen3b | qwen3b |

These are initial configurations, not proven optimal rankings. Earlier project tests at 4,096 context and Q4_K_M found Gemma 4 complied with three out of three small constrained tasks, while Glitter complied with one out of three; a separate single screenplay sample suggested lively Glitter banter. Neither study establishes long-form quality. This repo's default 8,192 context and longer outputs are different settings and need measurement.

The 12B weights are roughly 7–8 GB and prior tested process peaks were around 9–10 GB. They are unsuitable for assuming an 8 GB worker. GH-INFERENCE performs resource checks; use an adequately provisioned worker and measure at the requested context. The included library disables weight-cache storage above its configured cache size, so repeated fresh 12B jobs can redownload weights. Fresh-runner isolation is significantly slower than its resident pipeline API.

With two character proposals, a normal scene uses eight fresh jobs; three chapter reviews, planning, and a compact final audit bring nine scenes to roughly 77 jobs, before repairs or validation retries. There is no claim this finishes in a few minutes. The coordinator timeout is six hours in the optional Actions workflow; if it times out, resume from its artifact using resume_run_id on the next manual workflow run, or download the artifacts and resume locally. Keep the same backend; the saved request controls the profile on resume. Larger workloads need a separately measured execution strategy.

## Can embedded files just be put in a folder?

Only with their matching index, source IDs, encoder, and retrieval code. An embedding is a vector, not the original story analysis. Query vectors must use the same encoder and pooling method as the stored vectors.

Included:

- data/literary-corpus.json: 605 source analysis records, including disabled records and provenance limits.
- data/literary_rag.db: 605 precomputed vectors, source JSON, old retrieval projections, FTS tables, and encoder identifiers.
- data/MASTER_GUIDE.md: craft reference, selected by small section-level keyword matching.
- rag/: local MiniLM encoder, ingestion, and hybrid retrieval code.

**Important discovery:** all 605 bundled retrieval projections are older than the current document builder. The corresponding record JSON matches the current corpus, but newer fields were not part of the embedded text. Default keyword mode builds a temporary FTS index from the current source, so it does not need a model or use those stale vectors. It does not claim semantic retrieval.

For real hybrid retrieval, rebuild locally first:

```bash
python -m pip install -e '.[rag]'
python -m rag.ingest --json data/literary-corpus.json
```

Set retrieval_mode to hybrid in a new request. Rebuilding downloads the MiniLM encoder on first use, then computes vectors locally. Model files are cached by Hugging Face; they are not included in this repo. Ingestion resumes changed-content work and refreshes nonembedded record metadata. Hybrid mode refuses to run while the current document projections disagree with the index. The source JSON remains the authoritative record metadata.

No hosted embedding API key is needed. Merely copying a differently generated vector file into data/ will not make it compatible. The shipped corpus contains model-authored analytical drafts; source limitations and disabled records must remain visible.

## Inputs and communication files

Edit examples/harbor.json for premise, audience experience, character profiles, rules, initial knowledge, length, profile, and bounded retries. Use unique stable character IDs. initial_facts includes known_by, so an undisclosed fact need not enter every character's context. world_rules are treated as public constraints; place secrets in scoped initial_facts instead.

Each run produces:

```text
runs/project/
  request.json             # frozen input
  retrieval.json           # source IDs, mechanisms, guide excerpts, index status
  refinement.json          # developed first prompt, assumptions, and preserved choices
  plan.json                # planned developments; not canon
  state.json               # sole atomic authoritative accepted state
  packets/                 # exact scoped role inputs, instructions, and budgets
  calls/                   # per-role raw outputs, diagnostics, content-addressed IDs
  work/ch01-sc01/
    draft.txt
    distinct-0.txt
    review-0.json
    memory.json
    memory-review.json
    chapter-review.json    # only at chapter boundaries
  checkpoints/             # accepted state snapshots
  scenes/                  # recoverable text projections
  chapters/                # assembled chapter text
  final-review.txt         # compact audit, not full manuscript review
  story.txt
```

Only one process can write a run folder. state.json is replaced atomically; scene/chapter text files are regenerated from it after interruption. A hard kill can leave .lock; remove it only after confirming the coordinator stopped. If a process dies immediately after committing state, its human-readable checkpoint file may lag, but state.json still owns accepted progress.

Packets contain exact scoped prompts for debugging; calls contain model output and diagnostics. Both can contain private story facts. Do not commit run folders or share their artifacts without checking their contents. The CLI never stores tokens. User-authored initial facts, claims, beliefs, and accepted events are distinguished; quotation checks and model memory review reduce unsupported promotion but cannot prove truth.

## One workflow

The optional Story coordinator workflow is manual-only. Set its GH_AI_TOKEN repository secret for live execution, choose fixture or github and a model profile. It runs the same local coordinator and uploads output/checkpoints even when a step fails. Its optional resume_run_id restores an earlier coordinator artifact before continuing; artifacts expire after seven days. It does not auto-publish story text to the repository. Artifacts from public repositories can be accessible to others; use only material you intend to share there.

The separate Tests workflow exercises deterministic local checks on pushes and PRs. It does not dispatch inference or receive the inference secret.

## Implemented and remaining

Implemented: structured request/plan/review/memory validation; fresh role calls; supplied architect and distinct-writing briefs; scoped character memory; bounded scene repair; full-chapter review; evidence-linked memory with a second reviewer; frozen-input resume; atomic accepted state; current-source keyword retrieval; stale-vector guard; chapter/text export; live adapter; public CI recipes.

Not implemented: a UI, automatic lore extraction from arbitrary manuscripts, precise dependency-based rewrites, a complete character simulation, adaptive old-memory retrieval, unbounded multi-agent debate, DOCX export, concurrent scene generation, guaranteed originality, or a definitive human-authorship test. The “humanizer” role means editing for distinct writing, exactly as its brief states.

Tests cover three-chapter assembly/resume, rejected prose/memory leaving canon unchanged, private-context filtering, evidence validation, lock exclusion, request/backend isolation, approval gates, disabled retrieval, stale embeddings, and truncated-response repair, and mocked live-adapter freshness/model routing. They do not establish live model reliability.

## Source provenance and license

See PROVENANCE.json for the GH-INFERENCE source snapshot and file hashes. It includes the user's current local library changes, not just a released PyPI package. The upstream working tree was not modified. RAG source came from ronmin11/hacktxprep at the recorded commit, with explicit integration fixes. The original literary source texts are not bundled as story bodies.

Original orchestration code is MIT licensed. The vendored library retains its MIT license. Corpus analysis and guide provenance are documented rather than assigning new rights to third-party underlying works. Downloaded model weights have their own model terms; this code's license does not license those weights. Before deploying beyond a testbed, confirm the hosting service permits the intended inference workload; GitHub Actions is not assumed to be unrestricted production inference hosting.

## Full live test input

Select examples/silent-bell-full.json (or request_file=silent-bell-full in the workflow) for the comprehensive three-character, three-chapter test. The dedicated refinement result is passed into chapter planning. The attached architect brief remains on disk in full; its task-focused craft rules are sent to the planning worker to reserve context for the structured outline. The library runner is configured for a public 16 GB ubuntu-latest worker; each remote worker also checks actual available resources.
