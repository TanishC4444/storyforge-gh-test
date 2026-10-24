# Sequential story stress suite

Run **Sequential story stress suite** from Actions. It dispatches the established
full separate-runner living pipeline, waits for its terminal state, collects its
audit and readable-story artifacts, and only then starts the next case. It does
not replace the writing/review graph with a coordinator inference call.

To retry only the novel and its continuation, set `cases` to
`ensemble,ensemble-continuation`. Set `saved_draft_run` to the run containing its
existing opening draft to reuse that text without another writer call. Passed
format tests remain untouched; the continuation runs only after the novel earns
full approval.

| Order | Format / genre | Scenes | Target words/scene | Authored cast |
|---|---|---:|---:|---:|
| 1 | Short story / dark fairy tale | 4 | 350 | 6 |
| 2 | Novel / political science-fiction mystery | 4 | 1100 | 16 |
| 3 | Screenplay / heist thriller | 2 | 800 | 8 |
| 4 | Stage play / dark comedy | 2 | 550 | 6 |
| 5 | Audio drama / maritime horror | 2 | 450 | 6 |
| 6 | Comic script / science-fiction adventure | 2 | 300 | 6 |
| 7 | Continuation of case 2 / consequences of its actual climax | 4 | 1100 | 16 |

Twenty planned scenes, approximately 14,400 target words across independent
worlds plus one eight-scene continued world. Four locations and 70 initial facts
exercise the larger case. Every authored ensemble character appears in the
four-scene participant layout. Scene length targets guide the writing, with an
80% minimum for developed action. Exceeding the former 130% ceiling is advisory;
quality, pacing, non-repetition and factual approval remain mandatory. Longer
drafts are preserved for optional user shortening rather than rewritten solely
to hit a ceiling.

The author supplies conflict and dramatic function but deliberately does not
specify the culprit, discovery or decisive twist. The model must plant and pay
off evidence, change leverage and retain costs. The continuation imports only a
fully approved canon checkpoint and asks for consequences, not the same opening.
If its parent fails, it is recorded as blocked rather than restarted from empty
memory. Independent cases continue after ordinary child failures.

## Provider policy

The suite requires 45-second exponential Gemini outage backoff,
three bounded rounds and a maximum eighteen HTTP attempts per role call. Two
independent projects per model route may be tried; Flash-Lite remains the smaller
hosted fallback. Successful calls stop immediately. Respect
Retry-After; actual cooldown may be longer. All hosted roles remain hosted-only:
there is no silent or immediate local-model downgrade. Daily exhaustion, auth
errors and invalid output are not mistaken for temporary capacity; inputs and
partial drafts stay available instead of manufacturing approval. Sustained daily
exhaustion may require a later rerun after reset. The hosted context ceiling is
96,000 characters (192,000 for the hosted-only ensemble and its continuation); no memory is truncated to fit. Repeated source hashes are
shared losslessly in the request. Output ceilings reserve room for thinking
tokens and increase in delayed recovery rounds after incomplete generation.

## Reports and limits

## Resume a failed scene without starting over

Every pipeline run saves `story-recovery`, even after a failed gate. It contains
the last fully approved episode checkpoint with its complete memory, all available
scene drafts, and the first unfinished scene number. Provisional text stays
separate from accepted canon. These artifacts are retained for 30 days.

Run **Resume saved story** with the failed **child pipeline run ID**. Leave the
scene on `auto`. Choose `editing` to retain its written draft, `memory` to retry
factual processing, or `scene` to regenerate only the unfinished scene. Completed
earlier scenes remain unchanged. The helper uploads a backup before requesting
one native partial rerun; downstream scenes and checks run again as needed.
Older runs without stage labels fall back to their scene boundary. Native retries
use the source run's original code revision; the existing universe-continuation
input is separate and begins a new episode.

The full pipeline also accepts `saved_draft_run` to import a complete first-scene
draft into the current code without a new writer call. The source state and
initial canon must match, and the creative brief may differ only in length
policy. This supports the saved novel draft whose only rejection was its former
length ceiling. Imported prose receives fresh literary and memory checks; no
approval is inherited. Incomplete provider responses and other rejection reasons
cannot use this shortcut.

## Verification and recovery costs

Moderate scenes (up to 1,500 target words) use one coherent writer. Linked
editorial findings share an editor, so one structural problem does not launch
competing rewrites for every cited paragraph. Scene-specific genre goals keep
the test from collapsing into the same ferry argument in every format.

Factual workers receive an exhaustive canon ID/key index plus their full history
partition and any superseded records they reference. Final extraction findings
can trigger one targeted correction matrix and one independent verification
matrix; these additional runners are skipped when memory already passes. The
prose and full ledger stay source-bound. Failure of the recheck still blocks
acceptance. The final audit checks the exact recovered ledger/proof pair when
this branch runs; it cannot substitute an earlier passing proof.

`stress-suite-results` contains comparison reports, child links, failed job/step
names, actual audited word counts, and readable story artifacts. Original role
logs and detailed artifacts remain in each linked child run. A pass requires a
successful child plus all expected scene approvals and source-bound memory proof;
a missing audit is a failure, even if the workflow is green. Original drafts
remain available when checks reject them.

Human reading is still necessary for originality, character depth, repetitive
prose and whether the climax feels earned. The report explicitly leaves literary
assessment pending. Automated approval is not a claim of novel-length quality.

Each child has a 45-minute wall-clock cap including queue time. A timed-out child
is cancelled and must reach a terminal state before another dispatch. The parent
has a 350-minute limit; this is a several-hour bounded test, not a latency promise.
No recurring automation is created. Seven runs are not seven simultaneous
provider workloads; independent role partitions inside each child remain parallel.

Generate briefs with `python -m scripts.build_stress_suite`; validate without
provider calls using `python -m scripts.stress_queue --validate-only`.
# Hard situations and adaptive completion

Choose `harder-suite` in **Sequential story stress suite** to run five independent
cases serially through the full separate-runner graph:

| Case | Scenes | Target words/scene | What it challenges |
|---|---:|---:|---|
| Chronology / POV | 4 | 450 | Yesterday flashback between present-day scenes; reader knowledge must not leak into absent characters; historical resources cannot refill present state |
| Ensemble novel | 4 | 750 | Sixteen stable characters, full authored memory, distributed agency and persistent costs |
| Source adaptation: screenplay | 2 | 400 | Retell one fixed authored episode, preserving events, uncertainty, witnesses, custody and counted expenditure |
| Source adaptation: comic | 2 | 300 | The identical source and initial canon in drawable panels, with the same event constraints |
| Interruption / recovery | 2 | 350 | Deliberately stop before scene 2 on attempt 1; resume that boundary and compare the approved scene and full memory prefix |

Rebuild fixtures with `python -m scripts.build_harder_suite`. The adaptation
source is a fixed author-owned fixture, not output from a different generated
story and not an adaptation after its ending. These are live model tests;
unit fixtures do not establish literary performance.

Each incomplete case has at most one automatic checkpoint retry. The queue backs
up drafts and full canon first. Automatic stage selection rebuilds the scene only
when no compiled draft exists, retries memory when literary adjudication passed,
and otherwise resumes editing. It waits for the new Actions attempt before
advancing, never redispatches an uncertain POST, and downloads retry results into
a fresh directory to prevent an old passing audit from being reused accidentally.
Recovery cannot count as successful unless the previously approved text and
memory prefix are unchanged. The interruption case also requires evidence that
the deliberate interruption actually occurred.

**Queue completion is separate from story approval.** This suite completes its
assessment and preserves partial output even if a case still needs revision;
`report.json` retains `all_passed: false` and `quality_status: needs_revision`.
Child quality gates remain strict and may show a failed Actions attempt. A failed
case does not stop independent cases, and unverified prose never becomes canon.
Provider buffers remain enabled; no immediate local-model downgrade is introduced.
The original `stress-suite` keeps its existing failure-on-unapproved semantics.

Memory checking includes every source anchor for an owned multi-passage fact.
Recovery extraction only receives findings intersecting its owned passages, so a
radio-event correction cannot tell an unrelated ferry-dialogue batch to invent
that event under the wrong source IDs.
