# Storyforge GH Test

A public, file-based storytelling testbed using literary retrieval, fresh model runners, distinct-writing editing, and reviewed story memory. No Gemini and no UI.

## Current workflow: one run, multiple runners, real parallel branches

The **Story runners** workflow declares the runner jobs directly inside one GitHub workflow run. There are no nested inference-workflow dispatches. Every model role executes the included GH-INFERENCE worker on the runner GitHub has already allocated to that job.

The graph is explicit:

1. Prepare request and literary retrieval.
2. Refine the initial prompt, then plan three chapters.
3. Fan out participating characters into a matrix with up to three parallel fresh runners.
4. Reconcile their proposals, draft the scene, and apply the supplied distinct-writing brief.
5. Run **story quality and memory extraction in parallel** against the same edited scene and accepted-state snapshot.
6. If story review requests corrections, make one bounded repair. Verify changed prose and refresh extracted memory before proceeding. Unchanged candidates reuse their hash-matched review/extraction.
7. Independently verify memory, then commit accepted state. At chapter boundaries, review the complete chapter before committing its final scene.
8. Start the next scene from that committed state. At the end, collect per-job artifacts, chapters, and checkpoints.

Characters share an immutable starting state version and have scoped model inputs. Only the acceptance job writes the next authoritative state. A rejected scene or memory does not become canon. Model checks remain fallible.

Actual simultaneous execution depends on available GitHub runners and account concurrency limits. Later scenes are deliberately sequential because their starting facts depend on earlier accepted scenes. Fresh runners reset context; they do not increase a model's context window.

## Run it

Open Actions → **Story runners** → Run workflow.

- backend=fixture: deterministic plumbing test; no models or credentials required.
- backend=live: actual model inference **inside these jobs**; no GH_AI_TOKEN secret required.
- request_file=silent-bell-full: full story input, three characters, three chapters, nine scenes.
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
- data/literary_rag.db: 605 precomputed MiniLM vectors, source JSON, and older retrieval projections.
- data/MASTER_GUIDE.md: indexed craft reference, selected by small section-level keyword matching.
- skills/story_architect.md: the supplied architect brief in full; the planner receives its task-focused craft excerpt to reserve context for the outline.
- skills/distinct_writing.md: the user's complete editing brief. This is an editing role, not an authorship detector.
- skills/story_quality.md: evidence-based quality-review contract.

All 605 bundled embedded projections are older than the current document builder, even though their source record JSON matches. Default keyword mode builds a current-source FTS index and does not use stale vectors. For hybrid retrieval, rebuild first:

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
