# Why the previous story failed

The evaluated source is the four-scene export from run 39552359292, also supplied by the user. The workflow completed, but its literature was not acceptable.

## Evidence and causes

- Scene 2 loses its travel and approach, opens directly with a negotiation, and repeats Odysseus's request verbatim. Local paragraph editing cannot restore omitted dramatic development without authority to restructure.
- Scene 3 repeats the council and the same permission repeatedly. It corrupts Thestor into “The stor,” attributes a keeper's earlier words to Odysseus, and summarizes authorization instead of staging competing interests.
- Scene 4 repeats acquisition and council material before briefly summarizing the supposed climax. Raw serialization (`"}},`) survives in prose. The same statements of consent recur rather than causing different choices.
- “his voice measured,” “the weight of the bargain,” apron adjustments, resolute gazes, and abstract honor declarations substitute for character-specific pressure. These phrases are editorial signals, not proof of authorship.
- The charge supply is repeatedly called “fixed” without actually fixing a numerical count. Instructions were echoed rather than implemented.
- Period feel is mostly names, gods and an invocation. Material choices, rank, reciprocity, shame, household obligations and causal action should carry the ancient social imagination.
- The chapter-quality artifact passes broad checks while citing earlier passages as sufficient evidence of chapter development. Existing validators establish that evidence exists; they cannot establish that the judgment is sound.
- The expedited path allowed failed reviews to produce a provisional export and did not revise after final reviews. One passage editor failed and kept its original source. “Workflow success” and “literary acceptance” were different states but the artifact name obscured that distinction.
- Independent paragraph replacements lacked a structural view. They could preserve factual phrases while still copying or restarting an entire scene. The source hash prevented stale edits, not narrative regression.

## New run design

This is a fresh retelling, not a repair of corrupted canon. The old run supplies only its classical retrieval; old scenes and invented facts do not become accepted events. The new brief replaces conflicting dialogue, invocation and direct-address requirements throughout.

Flash is limited to six generation calls per run, including failures and retries: refinement, outline, the final whole-story audit, and a maximum of two critical editing rescues. A slot is reserved for the final audit; any final recheck can use Gemma. Gemma 4 31B receives character proposals, writing, two revision-depth experiments, skeptical scene reviews and memory work. All use a central file-locked quota reservation queue: 14k input TPM/24 RPM for Gemma, 220k TPM/4 RPM for Flash, conservative margins below the user's reported quotas. Gemma is capped at 120 generation requests per development run. These are run budgets, not a claim of control over unrelated account usage. Credentials are only read from environment variables or a private temporary file during local execution, never committed.

The existing Executor and CPU worker remain the fallback for API failure and malformed output. One bounded formatting/validation retry may use CPU; reviewers never silently become passes. Provider auth, unsupported-model/configuration, and quota failures open a per-process circuit breaker, avoiding repeated API attempts. Hosted usage, actual model, elapsed time and fallback warnings are recorded.

Both restrained and deep revisions are generated from the same draft. The first changes wording and redundancy; the second may rebuild resistance, disclosure, decision and consequence. Each candidate gets an evidence-backed assessment. Edit fraction is recorded as a diagnostic, not a quality score. A passing candidate with no mechanical failures is preferred; remaining concrete faults get at most two repairs. Failure stops final publication and retains checkpoints.

The humanizer sees scene purpose, prior material state, exact faults and full prose. The expanded skill permits structural repair, removes repeated beats and instruction leakage, preserves meaningful stillness, and explicitly handles third-person narration with no dialogue. This is more than replacing stock adjectives.

Deterministic gates block duplicate paragraphs/long sentences, direct speech, first/second person, headings, recognizable serialization, copied passages and extremely short scenes. They cannot prove subtle depth or catch every malformed artifact. Semantic review is still needed and is not infallible.

A final whole-story audit follows scene checks. Only an accepted whole-story result gets `FINAL_STORY.txt`; diagnostics and alternative revisions remain separate. No provisional export is mislabeled final. One API run uses one coordinator job to enforce global quotas; fresh role contexts remain isolated even though weights are hosted.

## Remaining limits

No prose heuristic can prove that every sentence is necessary or that a story matches Homer. Full-scene editing is used for this experiment because local edits failed to repair structural problems. The tradeoff is more tokens than paragraph-only edits. Account rate limits, safety filtering, network failure and CPU fallback can still affect runtime. Independent character suggestions are not automatically canon. Memory claims remain source-bound, and the author ledger must not be treated as universally known facts.

## Findings during the new experiment

The first hosted draft still substituted explanatory gestures for negotiation. A restrained pass mostly preserved that weakness. The expanded humanizer now includes positive examples for narrated offers and refusals, and guidance against replacing emotional labels with stock body language. The causal blueprint in `examples/troy-development-notes.json` gives each scene an actual tactic, an alternative and a material cost; its details are explicitly author proposals. It replaces contradictory generated plan details before any scene becomes canon.

The first scene is the controlled restrained-versus-deep comparison. Later scenes combine composition and deeper reconstruction, without paying for an unused first draft, restrained edit and extra review every time. Deep reconstruction works from the required events and identified faults, instead of using the bad sentences as a template. Causal improvement still has to pass review; larger edit distance does not prove improvement.

Provider failures exposed a CPU fallback error: Qwen controllers were capped at 8k even for large editing requests. Humanizer/refiner fallbacks now keep the configured 16k context. When local runtime dependencies are unavailable during local development, fallback uses the same published library's existing GitHub CPU runner. The workflow itself installs the established local worker runtime.

Editorial quotation casing/typography errors are normalized only when they bind to the actual source (case-insensitive recovery must be unique). Paraphrased or invented quotations still fail. This avoids sending a sound judgment through another expensive model call for a capitalization difference.

Token counting has a separate ten-second timeout. One transient 5xx retry is quota-reserved; auth, quota and unsupported-configuration failures open the circuit. Scene files and valid planning checkpoints are reused on continuation. Final whole-story repairs operate on affected scenes rather than requesting a large complete-story rewrite. The final recheck can use Gemma, preserving the Flash cap.

Character proposals now run concurrently with separate packets and one shared token limiter. They receive their own approved knowledge and visible setting, not future scene outcomes or spoiler-bearing author world rules. API failures are requeued on the coordinator for the existing CPU fallback, avoiding worker-thread signal-handler failures.

The new run also exposed a deeper identity failure: an otherwise coherent candidate made Thestor the blind priest, and a reviewer without the cast definitions passed it. That candidate was rejected before canon. A compact cast registry now accompanies both creation and audits, while isolated actors receive only their own identity. A deterministic guard also blocks the observed Thestor/priest conflation.

The remote CPU fallback had not been forwarding the existing library's structured-decoding option. This allowed a failed memory controller to enumerate hundreds of approval indices until truncation. The adapter now forwards the JSON schema, and the ledger's approval array is bounded to the actual number of proposed memories with an explicit index enum. Public-memory scope is forbidden in this experiment: a Greek council is not public knowledge for Hector. Unsupported public claims are quarantined rather than silently broadened or narrowed.

One first-scene memory recovery was reviewed directly by Codex against the exact accepted prose and recorded with evidence spans and provenance. No new scene events or private knowledge were invented, and no prose was changed in that recovery. This is documented intervention in this development run, not a claim that the failed extractor passed.

The failed identity candidate and controller outputs remain in diagnostics. The corrected second scene passed a cast-aware review, and the fallback ledger completed with a bounded approval array: six weapons, twenty-four remaining charges after one demonstration, and the seal/basin obligation. Source-bound extraction and approved witness lists are kept separate from the author's continuity record.

## Delivery

The final publication is `outputs/troy-third-person/FINAL_STORY.txt` (four scenes, about 3,700 words). It includes a direct Codex editorial pass after the API-generated scenes; this is recorded separately rather than attributed to Gemma. The exact edited body passed a fresh compact Gemma whole-story review. `final-state.json` is the canonical handoff for that published text; pre-editorial run snapshots are diagnostics, not the final prose authority.

The editorial pass clarified physical handling, removed abstract significance summaries, corrected an unexplained limp and cavalry language, made the spoiled charge return to use through rain and handling under attack, replaced an unsupported damp-powder pressure claim with a misfire and unstable support, and made the final counts explicit. The ending now acts on the outstanding obligation instead of announcing its meaning.

The development run executed from the local coordinator, using hosted APIs and the same published library’s GitHub CPU fallback when needed. The committed Actions workflow supports future runs with an encrypted repository secret, phase log groups, and a separately named `FINAL_STORY` artifact. The classical retrieval can fall back to its committed cache if the old Actions artifact expires.

The first raw whole-story review passed prose that still needed editorial work; model approval was not treated as sufficient proof. A separate final mechanical check also exposed that scene dividers were being counted as repeated prose. Dividers are now exempt while real duplicate paragraphs still fail, with regression coverage. Invalid memory approval indices are quarantined, and inconsistent reported usage is withheld rather than silently converted into a firing event.

The final publication review used Gemma after the six-call Flash role budget had been consumed. A compact candidate-only review avoids sending obsolete pre-editorial ledgers back as narrative authority. The run reserved 82 Gemma generation attempts and six Flash attempts, including failures and retries; one small connectivity generation probe for each model was outside that orchestration counter. These are development-run figures, not an estimate of every future story’s cost or a guarantee of latency.

## Full-flow efficiency and failure audit (21 October 2026)

The latest pre-optimization run, 39629417302, failed in refinement, not writing.
Flash returned HTTP 503 after its bounded transport retry. The CPU fallback's
first response took 521 seconds and failed the exact original-prompt echo check;
the second took 830 seconds and exhausted 3,600 output tokens. Schema compliance
alone cannot enforce equality with immutable user text or guarantee natural completion.
The application now binds that original prompt itself and retains the raw response.

In completed run 39552359292, the scene-4 writer job took 925 seconds, and scene-3
and scene-4 story-quality jobs took 653 and 627 seconds. These are job wall times,
including setup, rather than pure API latencies. The fast profile assigns both roles
to the larger Qwen 2.5 7B CPU model. Large, repeated context and substantial output
make them slower than short control calls. The failed API runs did not reach those
stages, so they provide no end-to-end API speedup measurement.

The full API workflow now uses one resident coordinator. It still performs fresh
hybrid retrieval, refinement, development review/revision/gate, outline and its
review/revision/gate, scene reconciliation, isolated actor proposals, direction,
writing, humanizing, review, repair, changed-text verification, memory verification,
canon commit and final chapter review. It does not use the retelling experiment's
fixed development overlay or prior accepted scenes. Development checks share one
call; story and rhetoric share one source read with all sixteen checks; accepted
text is recorded once after editing. Unchanged prose reuses its hash-bound review.

Gemma is the primary hosted route; scarce Flash calls are reserved for at most two
rescue routing attempts and the final chapter audit. Both routes retain the CPU
fallback. Provider errors do not become approvals. Gemini uses native JSON schema
configuration; Gemma receives the explicit schema in its prompt without assuming
Gemini JSON-MIME compatibility. Model health, bounded retry/circuit state and quota
counters are shared across stages. Conservative token pacing includes reserved
output. HTTP telemetry keeps model, operation, duration and allowlisted status only;
provider messages, credentials and prompts are excluded from that telemetry.

The four main authoring/planning/review skills fell from 28,741 to 7,115 bytes
(75% smaller). Source limits and requested reference mechanisms remain in scoped
packets; full retrieved material and original requests remain in checkpoints.
Reduced prompt size does not establish higher literary quality; that requires
inspection of the resulting prose and reviews.

Canon has an append-only source-bound history and a current-state projection.
Changes cite prior fact IDs with the same fact key and kind; arbitrary or future
supersessions are rejected. Actor visibility is applied before current-state
projection, so a character who never learned a change retains their older knowledge.
Older resources, relationships and unresolved threads are prioritized over routine
recent events; omitted working-context IDs are explicit. Full evidence and all
historical versions remain in canon.json and snapshots. Planned reference uses and
source-bound model assessments remain in reference-usage.json. The current index is
not an independent semantic oracle: model-generated updates still require the
separate memory verifier and unsupported updates remain quarantined.

FINAL_STORY.txt is emitted only for a completed reviewed result. An unresolved
result is named PROVISIONAL_STORY.txt, with its review report, rather than receiving
a final-story label. phase-timings.json, benchmark.json, provider-health.json and
provider-budget/requests.jsonl distinguish stage time, output generation, provider
failure and quota pacing. The new orchestration has full fixture coverage; actual
speed, provider availability and literary quality must be measured on its live run.

## Usage recording and run 39646990809

The restored multi-runner run failed in planning. A prior Gemma HTTP 500 opened
its inherited circuit; the planner's first CPU response used misordered scene IDs
and numbered chapters as 2, 3, 4, 1. The second hosted attempt also returned HTTP
500; its CPU fallback put the IDs in order but numbered the four scenes as chapters
1, 2, 3, 4, rather than keeping all in chapter 1. Schema-level numeric ranges did
not prevent that transport output. Scene IDs and chapter numbers are now
application-owned metadata derived from requested reading order. Scene content is
never reordered or approved by that assignment; development review remains required.

Earlier in the same run, the batched development review needed 8,733 tokens but the
CPU fallback was limited to 8,192 despite the configured 16,384-token context.
Compact structured calls now retain the configured context. The review was marked
unverified; the draft-continuation policy allowed planning to proceed provisionally.

Usage is now recorded for every returned CPU attempt and each hosted generation
attempt, including retries and truncated provider output. Google usage is saved
before finish-reason rejection. HTTP failures without usage metadata retain null
counts, never invented zero usage. Count-token estimates and quota reservations do
not enter observed token totals. Prompt text and credentials are excluded.

Every story workflow saves JSON, CSV and readable usage reports as a separate
usage-RUN_ID artifact retained for 90 days, including failed runs. Reports group
provider, model and role, with request counts, observed input/output/thinking/total
tokens, unknown usage counts and elapsed attempt time. These are observed usage
records, not invoices or account quota balances.

The recovered historical report under reports/run-usage/39646990809 contains three
CPU outputs totaling 17,849 input and 2,012 output tokens (19,861 total), plus six
hosted generation attempts whose token metadata was not preserved by the old
instrumentation. One hosted response hit MAX_TOKENS before CPU fallback; that
successful HTTP response was not a successful accepted generation. Its token usage
cannot now be reconstructed. The report explicitly marks all six as unknown.

## Bounded API batch experiment

The next multi-runner experiment preserves the same Troy discovery/acquisition/
trial/first-use brief and the full separate-runner graph. Gemma handles development
review groups of four checks and story-quality check batches. Flash handles
source-bound memory-update batches and the final chapter audit. Refiner, planner,
writer, humanizer, character and director roles retain their CPU workers. This
isolates hosted services from scene-length generation and metadata assignment;
it does not guarantee that provider 5xx errors disappear. Small four-item batch
probes save compatibility results before the run proceeds. Flash's final generation
slot is reserved for chapter review; ordinary batches fall back when that allowance
is exhausted. Live timings and probe outcomes must establish whether reliability
or speed improves.

The user wants to conserve the ChatGPT/Codex account quota used in this
conversation. Keep responses and investigation concise and avoid redundant polling
or checks. A local account-wide snapshot was saved under reports/chat-usage/ and
excluded from Git; do not infer per-chat use or continue routine sampling without
an explicit request. Separate story-model token reports remain workflow diagnostics.

## Separate parallel-efficiency experiment

`troy-parallel-experiment.yml` is a separate generated multi-runner workflow. The
original multi-runner workflow remains available. Refinement/review/revision/gate
and planning/review/revision/gate each share one runner; editing stays a whole-scene
distinct-writing pass. Repair, changed-paragraph verification and memory refresh
jobs are gated by explicit outputs, with conditional artifact downloads and accept
fallbacks when those jobs are skipped. Setup-worker is unchanged.

The opt-in worker policy supplies per-stage hosted tiers, supported thinking levels,
output caps, request timeouts and bounded retries for fast/small profiles. API
requests share a per-process semaphore. CPU inference is serialized because the
resident model and runner RAM cannot safely support several heavy completions at
once. Retried API requests and failures are counted by stage/status in events and
status files. Artifact-carried provider reservations still pace distributed stages;
this is not an account-wide semaphore across unrelated workflow runs.

Story/rhetoric dimensions run concurrently inside their respective jobs. Findings
include severity and a zero-based paragraph index, or null for a whole-scene issue.
Repair groups findings per paragraph, generates patches concurrently and applies
them against an immutable hash in reverse source-offset order. A global repair pass
runs only for null-paragraph findings. facts_changed is conservative: any prose
change refreshes affected memory rather than trusting a model's claim that facts
were unchanged. Verification receives the diff, prior findings/assessments and canon
context, not an unchanged full-scene resend; a final chapter audit remains required.

Initial extracted memory is independently verified. Diff refresh retains only
unchanged, source-rebound facts from that verified base, extracts from changed
passages, and independently checks changed facts. Missing verification triggers the
safe full-source path; quarantined facts are not silently promoted to canon.

writer_beats controls an independent beat-writing experiment. A short plan defines
entry/exit states, beat drafts run concurrently without prior beat prose, and seam
editors own only the following beat's first paragraph. The planned exit is not an
observed generated exit; whole-scene editing and continuity review must catch any
mismatch. Set writer_beats to 1 to disable this feature alone if quality suffers.

Next-scene design may start from an explicitly speculative snapshot while the
current scene is reviewed. Characters and writing wait for settle: after canon
commit it compares the speculative memory hash with actual accepted memory. A
mismatch reruns design inline against accepted canon. Speculative facts never become
canon merely because the design job ran.

Knobs live under execution_policy in examples/troy-parallel-experiment.json:
gate_repair_threshold, writer_beats, and per-kind concurrency. Fixture tests cover
both repair gates, patch ownership, beat stitching, source fallbacks, a complete
two-scene sequence, delta-only verification and forced hash-mismatch design reruns.
Live speed and quality improvements remain unmeasured until the experiment runs.

## Large story revision (2026-10-21)

The experimental request now targets three chapters of four 1,200-word scenes
(about 14,400 words). The rich supplied brief is compiled directly into the
refinement contract, with no generative refinement/development loop. Outline
creation, critique, revision and gate run separately for each four-scene chapter;
scene IDs are rebound to their true chapter after local validation. There is no
claim that independent chapter reviews establish whole-story literary quality.

Creative work and substantial judgments use existing CPU workers: outline,
development, direction, whole-scene drafting, structural chapter-aware revision,
line editing, repair, story/rhetoric audits, memory extraction and chapter audit.
Only bounded character proposals and fact-verification calls use the hosted API.
The new CPU quality option uses the existing qwen7b model for substantial stages.
Removing API dependency does not imply faster creative generation on CPU.

Current-chapter prose, scene contracts and canonical prior facts guide revisions.
Earlier chapters remain in checkpoints and source-bound canon; they are not all
repeated in every model input. Each scene gets two whole-scene revision passes
before any review or memory extraction. There is no late chapter rewrite that
would invalidate recorded facts. Deterministic guards reject quoted speech,
invocations, headings, identical substantial paragraphs and, in live runs,
undersized/oversized scenes. Failed review gates stop canon acceptance instead of
silently declaring a provisional draft final. These checks cannot prove literary
excellence; live prose and quality still require inspection.
