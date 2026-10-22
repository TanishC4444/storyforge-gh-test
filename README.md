# Storyforge GH Test

Latest completed experiment: [FINAL_STORY.txt](outputs/troy-third-person/FINAL_STORY.txt) — four scenes, third-person narration, no dialogue, with a final editorial pass. [Workflow and writing audit](docs/RETELLING_AUDIT.md).

A public, file-based storytelling testbed using literary retrieval, fresh model runners, distinct-writing editing, and reviewed story memory. No Gemini and no UI.

## Current workflow: one run, multiple runners, real parallel branches

The **Story runners** workflow declares the runner jobs directly inside one GitHub workflow run. There are no nested inference-workflow dispatches. Every model role executes the included GH-INFERENCE worker on the runner GitHub has already allocated to that job.

The graph is explicit:

1. Prepare request and literary retrieval.
2. Refine the initial prompt, critique it, revise if needed and recheck; repeat that development loop for the three-chapter outline. Reconcile each scene against accepted events before character proposals.
3. Fan out participating characters into a matrix with up to three parallel fresh runners.
4. Reconcile their proposals, draft the scene, and apply the supplied distinct-writing brief.
5. Run **story quality, rhetoric quality and memory extraction in parallel** against the same edited scene and accepted-state snapshot.
6. If story or rhetoric review requests corrections, make one bounded repair. Verify changed prose and refresh extracted memory before proceeding. Unchanged candidates reuse their hash-matched review/extraction.
7. Independently verify memory, then commit accepted state. At chapter boundaries, review the complete chapter before committing its final scene.
8. Start the next scene from that committed state. At the end, collect per-job artifacts, chapters, and checkpoints.

Characters share an immutable starting state version and have scoped model inputs. Only the acceptance job writes the next authoritative state. A rejected scene or memory does not become canon. Model checks remain fallible.

Actual simultaneous execution depends on available GitHub runners and account concurrency limits. Later scenes are deliberately sequential because their starting facts depend on earlier accepted scenes. Fresh runners reset context; they do not increase a model's context window.

## Run it

Open Actions → **Story runners** → Run workflow.

- backend=fixture: deterministic plumbing test; no models or credentials required.
- backend=live: actual model inference **inside these jobs**; no GH_AI_TOKEN secret required.
- request_file=silent-bell-deep: default detailed brief with character arcs, owned subplots, physical causality, scoped classic references and figurative-language controls; three chapters, nine scenes.
- request_file=silent-bell-full: earlier compatible test brief.
- profile=balanced: Gemma 4 for control, writing, editing, and review.
- profile=expressive: Glitter for writing, Gemma 4 for other roles.
- profile=small: Qwen 3B baseline.
- scene_limit=1: check one scene's full runner graph first.
- scene_limit=9: full three-chapter run.

The live target is approximately 850 words per scene, about 2,550 words per chapter. Fixture scenes are deliberately short and labelled; they are not model-generated fiction or evidence of literary quality.

The workflow has explicit slots for this three-chapter, three-scene-per-chapter test. `scripts/build_workflow.py` generates its checked-in YAML. The many visible jobs correspond to actual role boundaries, file transfers, optional repair checks, and canon commits. Lightweight forwarding stages avoid new model calls when their candidate is unchanged.

Runtime setup uses Python 3.11, the vendored GH-INFERENCE library, and its llama-cpp-python 0.3.36 worker. The larger models require adequately provisioned runners; model/context RAM and free disk are checked. The public ubuntu-latest budget is configured as 16 GB; the worker checks actual available resources too. Initial model/runtime downloads and repeated fresh-runner startup can make the full test take hours.

## Files and artifacts

Each job uploads its own artifact, containing only its products plus its scoped packets and diagnostics. Downstream jobs download required artifacts. Runners do not rely on another runner's uncommitted working directory.

```text
prepare / refine / plan
  snapshot.json          # request, refinement, plan, accepted state
s01_characters-mara
  proposal.json
  packets/               # actual scoped model input
  calls/                 # raw output, timing, workflow/job identifiers
s01_edit
  prose.txt
s01_story
  review.json
s01_memory
  memory.json
s01_accept
  snapshot.json          # next authoritative version, only after checks pass
  scenes/
  chapters/
  story.txt              # present when all three chapters are accepted
```

Final artifact: `story-run-<workflow run ID>`. Its folders preserve the per-job products, including failure evidence. Intermediate artifacts are also downloadable individually. Artifacts expire after seven days; download what you need. This is a public testbed: use story material you intend to share.

To retry infrastructure or malformed-output failures, use GitHub's failed-job rerun facilities; previously successful upstream artifacts remain available. Semantic review failures need actual corrections, not repeated acceptance of the same rejected draft. One automatic prose-repair round is declared in the graph. A still-rejected scene, a rejected memory update, or a chapter-level rejection stops continuation. There is no claim of unrestricted automatic recovery or precise dependency-based manuscript rewriting.

## RAG: what is included

- data/literary-corpus.json: 605 analysis records with provenance and disabled-record flags.
- data/literary_rag.db: 605 freshly rebuilt MiniLM vectors, source JSON, and revision-pinned retrieval projections (603 eligible records).
- data/MASTER_GUIDE.md: indexed craft reference, selected by small section-level keyword matching.
- skills/story_architect.md: the supplied architect brief in full; the planner receives its task-focused craft excerpt to reserve context for the outline.
- skills/distinct_writing.md: the user's complete editing brief. This is an editing role, not an authorship detector.
- skills/story_quality.md: evidence-based quality-review contract.

The bundled index has been rebuilt against the current document builder, with zero stale projections. The deep brief uses hybrid retrieval; preparation installs the optional retrieval dependencies. To rebuild after changing the corpus:

```bash
python -m pip install -e '.[rag]'
python -m rag.ingest --json data/literary-corpus.json
```

The encoder downloads on first use, then embeddings compute locally. No hosted embedding key is required. Hybrid mode refuses stale projections. Copying arbitrary vectors into a folder is insufficient: source IDs, encoder, dimensions, and pooling must match. Corpus analyses are model-authored drafts with recorded source limitations.

## Local checks and compatibility CLI

Python 3.11+ with SQLite FTS5:

```bash
python -m unittest discover -s tests -v
```

The local tests exercise all nine scenes with isolated parallel branches, provenance/evidence validation, failure leaving canon unchanged, private knowledge filtering, refinement handoff, and worker-backend routing without remote workflow dispatch. They do not establish live literary quality.

The older sequential CLI is retained for comparison and local checkpoint debugging:

```bash
python -m storyforge.cli --request examples/harbor.json --out runs/fixture --backend fixture
```

Its optional github backend uses the library's older separate-workflow dispatch path and requires GH_AI_TOKEN. **That CLI is not the implementation used by the current Story runners graph.** Earlier launch notes and fixture examples describe the previous path; they are not evidence for the current live run.

## Scope and provenance

The prototype retains all accepted prose and memory, but working memory currently selects recent records within count and character budgets. Important old facts can be missed. There is no perfect-memory claim, unrestricted world simulation, UI, DOCX export, automatic early-scene dependency repair, or guaranteed originality.

See PROVENANCE.json for source commits and vendored-library file hashes. The user's upstream library checkout was not modified. Original orchestration code is MIT licensed; the vendored library retains its MIT license. Corpus/guide provenance and downloaded model terms remain separate. Confirm permitted hosting use before treating any test arrangement as production inference infrastructure.

## Refinement recovery

Equivalent structured presentation is normalized without inventing content: a reader-experience list becomes a joined string, and labelled mappings become name/value entries. Missing required information still fails validation. The optional refinement_seed_run workflow input reuses a prior refine artifact only when its original story request matches and its content passes current validation; this avoids regenerating an already-written refinement after a formatting-only rejection. The raw model output and recovery provenance are preserved.

## Source-bound memory evidence

Memory extraction now selects stable paragraph IDs from an ordered evidence catalog; the application resolves exact source text, offsets, and prose hash. Legacy quotes allow only unique source matches after whitespace/typographic-quote normalization or removal of an enclosing quote wrapper. Paraphrases, unknown IDs, ambiguous normalized matches, and stale-prose evidence remain rejected. A source match does not prove the proposed fact or speaker attribution; the separate memory-quality gate still applies.

## Creative coverage and editorial audit

See [the pipeline audit](docs/CREATIVE_PIPELINE_AUDIT.md), [deep test input](examples/silent-bell-deep.json), [actual hybrid retrieval output](examples/rag-output-deep.json) and [scoped writer packet](examples/rag-writer-packet.json). Story and rhetoric reviews require complete evidence-linked check coverage; initial design and outline reviews cover the creative categories before drafting. These automated gates remain fallible. The compatibility CLI does not implement the full DAG editorial pipeline.

## Troy opening movement

The manually dispatched **Troy story runners** workflow uses `examples/troy-first-thunder.json`: one chapter, four scenes, about 1,400 words per scene, with discovery and acquisition preceding first battlefield use. The expressive profile uses Glitter for drafting and Gemma for control, editing and review. All roles remain native jobs in one workflow. The original nine-scene workflow is separate.

Explicit `retrieval_weights` now apply mathematical weights to normalized reciprocal semantic/keyword ranks and controlled-mechanism overlap, summed over weighted query facets. The Troy brief uses 0.60 / 0.15 / 0.25. Explicit source references are pinned separately; adaptation strength still controls requested literary influence rather than measuring borrowing. `examples/troy-retrieval.json` records the real retrieval result. The four-scene stress fixture passed with 1,400 synthetic words per scene; it is not a literary-quality or exact-token benchmark.

## CPU runtime budgets

Both native story workflows allow **360 minutes per job**. A shared deadline gives inference and its validation retries the remaining job time, with five minutes reserved for cleanup and artifact upload; the former 35-minute subprocess cap is removed. The compatibility dispatch adapter also receives a six-hour job/completion budget. Download socket timeout is ten minutes, separate from generation duration. These settings change time budgets, not model context, RAM, output length or editorial acceptance rules.

The first Troy attempt (39472094367) completed refinement but GitHub cancelled its development review at 45 minutes. Recovery uses that run's `refine` artifact through `refinement_seed_run`, validates the exact request, and retains the original refinement rather than generating it again. A new run is necessary to execute the changed workflow revision. Development review now receives a catalog of actual candidate paths, preventing the observed mistake of treating normalized arrays as invented named fields from being silently accepted.

## Faster Troy execution (gh-inference 0.6.1)

The live workflow installs the published 0.6.1 PyPI wheel by its immutable URL and SHA-256, avoiding stale package-index metadata. `ResidentSession` retains one model's weights within a job and resets token context for each request. Independent GitHub jobs still have separate RAM and fresh runner contexts.

The expressive profile keeps Glitter drafting and Gemma literary editing/review. Qwen 3B handles scoped developmental checks, character proposals, scene reconciliation and memory tasks. Twelve developmental checks run in four focused groups; evidence IDs resolve to actual source locations in code and JSON decoding constrains allowed identifiers. The saved Troy candidate's largest review packet shrank from 33,716 to 7,068 input characters (not a token or speed benchmark). Unchanged passing designs reuse a hash-matched assessment rather than paying for an identical second review. Changed designs still require reassessment.

Code validates counts, identifiers, source bindings and context budgets. Formatting repairs receive only the invalid output, validation error and allowed IDs; a parseable review's judgments and reasons must remain unchanged. Failed content checks do not become formatting passes. Resident sessions count tokenized content, reserve requested output and template allowance, and reject overflow without truncation. Six-hour job budgets remain in place.

The library's real GitHub resident-session smoke test passed two isolated constrained-JSON calls using one loaded model. Standard runners remain CPU-only; optional GPU offload requires a separately provisioned compatible host. No GPU speedup is claimed. Fixture tests do not establish literary quality or live Troy performance.

### Duplicate-check regression

Run 39503852240 failed because the reviewer produced two world-rule assessments and omitted character depth. The previous array schema constrained IDs and count but did not enforce one assessment per distinct ID. Developmental and prose-review decoding now require a checks object with each category as a mandatory named property. The application converts these keyed assessments into stored review records. The actual failed response is preserved as a regression fixture; missing checks remain rejected. This contract change has not yet been tested in another live story run.

## Following a live job

Open a job and expand its **Execute …** step. Timestamped logs identify state loading, retrieval, recovery, each development-review group (1–4), model and attempt, packet size, output/context budgets, validation, repairs, reused reviews and canon commits. During native inference, an elapsed-time heartbeat appears every 20 seconds. It means the call is still active, not that the model has made a particular percentage of progress. Model loading, prompt evaluation and generation are not separately observable until the response returns; completed-call timings then report the available breakdown.

Each job artifact contains `status.json` (latest state and error), `events.jsonl` (timeline), `calls/` (raw outputs/timings) and `packets/` (scoped inputs). GitHub job summaries list phases, validation counts, accepted-scene progress when available, errors and a direct artifact link. Summaries publish as their steps finish; live progress is in the logs. Setup/download failures are visible in their own Actions steps even if the story task never starts.

## Fast draft continuation and targeted fixes

The Troy request now uses `fast`: Qwen 7B drafting and story review, Qwen 3B control/rhetoric/memory/targeted editing. This changes the quality/performance tradeoff; no new live speed or literary-quality result is claimed. The expressive profile remains available.

The writer receives the distinct-writing brief directly. The edit stage forwards its draft; story and rhetoric reviewers run in parallel and can return paragraph replacements with their issues. Source-bound fixes are applied without regenerating untouched prose. Conflicting or missing replacements receive one focused edit call containing only affected paragraphs and the brief. The full-scene rewrite and extra director model call are removed in fast mode. Changed prose still receives review and fresh memory extraction.

Memory output is schema-constrained (required wrapper, supported kinds/characters, at most three evidence IDs per fact). Bare outer arrays can be wrapped losslessly, duplicate IDs removed, and individually invalid entries quarantined. Evidence is never arbitrarily truncated to force a claim through validation. If extraction or verification fails, the source scene is retained and unsupported facts are withheld. The writer also receives explicitly author-only prior-scene excerpts; these do not grant character knowledge.

`execution_policy.continue_with_warnings` explicitly opts into **provisional draft continuation**. Unavailable or negative reviews remain unavailable/negative; they are not converted into passes. Scenes can be checkpointed with `quality_status=needs_review`; exports carry a provisional banner and `editorial-report.json`. Completed drafts with unresolved checks are `complete_with_warnings`. Strict requests continue to reject failed gates. This policy handles recoverable content/format failures, not every possible infrastructure outage.

The checked-in recovery seed preserves the previous live outline, refinement, source-matched reviews and 1,115-word scene 1. The creative brief must match before reuse; execution settings may differ. Seeded preparation skips embedding-runtime installation, planning is reused, and scene 1 is not redrafted. `recovery/troy-39512585096/scene-01.txt` is the original unapproved scene, not a newly corrected result.

The full four-scene fault fixture completed with warnings while injecting malformed memory, unsupported memory facts and reviewer outages. These tests verify recovery and accurate warning labels; they do not establish live completion or prose quality.


## Prose recovery and parallel chapter outlines

The twelve-scene Troy experiment develops its three chapter outlines on separate
Actions runners from the same immutable brief. Each chapter retains its complete
development review/revision/gate sequence. A lightweight join checks snapshot
hashes, rejects missing or duplicate chapters, restores reading order and validates
the full plan. Retrieval runs once upstream and travels with every chapter packet.
Actual overlap depends on available GitHub runners.

Whole-scene drafting, structural revision and line editing validate prose within
the existing bounded retry loop. Live strict-length scenes must meet the configured
word range before advancing. A retry receives the rejected prose, exact validation
error and original context; raw outputs remain in calls/. No quotation marks are
silently stripped. Repeated failures stop before publication and canon acceptance.
Structural and line edits remain ordered; story, rhetoric and memory branches stay
parallel. CPU inference inside each runner remains serialized to avoid competing
model loads; separate runners provide the additional chapter parallelism.

Validation uses fixture and mocked-model regression tests; it does not establish
live prose quality or a measured speedup.
