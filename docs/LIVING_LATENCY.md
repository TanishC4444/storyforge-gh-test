# Living practice latency

The reference is successful Living Actions run **39856538428**, completed in
14 minutes 4 seconds on 2026-10-22 UTC. Its final memory batch alone ran for about
five minutes. A roughly 15-minute target applies to one 900-word event with
available hosted capacity and prompt runners, not a guaranteed bound for four
chapters or a quota outage.

Living keeps the classic separate-runner stages: prepare/retrieval, local event
direction, scene design, character proposals, direction, coherent writing batches,
parallel story/rhetoric checks and memory processing, targeted repairs, one strict
judgment when needed, verified memory, acceptance and readable output collection.
The newer summary and final section allocation/summary/join matrices are removed
from this workflow; Cinematic retains its existing graph.

All nine story and eight rhetoric dimensions remain. The story and prose review
each see the whole current scene as one coherent batch. Repetition, chronology,
actor knowledge, custody, resource counts, POV and author style still matter.
Unchanged text can reuse passing reviews only when source and state match and the
full factual proof matches source, state and extracted memory hashes. Changed
text, failed checks or stale proofs require one strict final model judgment.
No automatic literary approval is added.

Memory remains complete: source extraction and every required fact/history/source
partition remain in separate matrices. Only unchanged, already verified memory
reuses its proof. Changed evidence is extracted and checked again. Facts are not
replaced by a smaller literary summary.

Hosted Living jobs skip CPU inference installation and CPU fallbacks. Optional
provider failures preserve readable drafts and explicit warnings; a failed factual
proof cannot publish canon. Matrix concurrency remains two editorial/three memory
jobs; per-call HTTP attempts remain capped. Known model-specific project cooldowns
are skipped using local health, not live API probes. This is not a distributed
quota service.

Validation runs the generated first-scene dependency graph with fixture transport,
including real artifact handoffs, all editorial dimensions, memory checks and
canon acceptance. It also checks that changed text receives one strict judgment.
Fixture completion proves wiring, not live speed or prose quality. End-to-end live
time must be measured from a new run.

## Larger-episode pipeline

`living-universe-pipeline.yml` keeps separate character, writer, reviewer, editor,
source extraction, factual checking, final judgment and acceptance runners. It
fuses only deterministic plans/joins/copies into their adjacent role stages. The
stable `living-universe.yml` remains available as the measured one-scene baseline.
The next writer still waits for the prior acceptance and source-verified factual
handoff; future plans never count as memory.

The scale practice uses two 900-word scenes, twelve named characters (four active
participants per scene), 24 world rules and 96 distinct starting facts. Its
memory matrix retains all prior history and crosses every new-fact partition and
source window with every history partition. Larger 32-record history partitions
and six bounded concurrent memory runners reduce scheduling overhead; no history
is discarded. POV facts can reference IDs in the complete author ledger to avoid
copying identical records twice without granting access to private facts.

The larger cast is indexed by ID/name in scene design; detailed profiles are sent
for the current participants. Complete character definitions remain in the author
request, and all their memories remain in the factual audit. Explicit resource,
belief and thread types on initial facts now survive preparation instead of being
silently relabeled as events.

Reported narration is permitted when the author's specific rules permit it;
reviewers must not invent a prohibition on indirect speech-reporting verbs. Real
repetitive bargaining remains reviewable. Targeted patch output budgets accommodate
actual paragraph replacements instead of truncating them behind reasoning tokens.

An additional final episode audit requires actual literary approvals, committed
canon, exact source/state/fact proof bindings and preservation of every initial
fact. A green generation job alone does not pass this audit. Live runtime and prose
quality still need to be measured from the newly generated run; fixture tests are
not speed or quality claims.

Hosted pipeline calls transport the full response grammar through the provider's
native schema rather than also echoing that grammar into the prompt. Application
validators are unchanged. Final reviewers receive the failed/disputed earlier
checks and all issues, while independently reassessing all 17 dimensions; repeated
passing explanations are omitted. A measured stress packet with the previous
900-word output fell from over the 48,000-character limit to 41,085 characters,
with all 96 initial facts retained. This measures packet size, not live quality.

Pipeline jobs explicitly check immediate dependency results with status functions,
so a deliberately skipped no-change refresh cannot silently skip acceptance or
later scenes. Upstream artifacts are fetched once in parallel and mapped locally
to explicit aliases; duplicate aliases no longer trigger repeated downloads.
Hosted-only workers import the dependency-free checkout directly instead of
reinstalling it for every role. An empty writer response now marks that job failed
while retaining diagnostics, enabling a targeted retry.

The scale brief explicitly permits a 64,000-character hosted context budget;
extended budgets are rejected unless all routed roles require hosted inference.
This accommodates actual memory growth without silently dropping facts or
falling back to an undersized CPU context. Strong review routes can try Flash 3.6
then Flash 3.8 within the same two-HTTP-attempt cap.

The optimized pipeline compiles actor packets from authored profiles and exact
knowledge allowlists instead of requesting an optional model tactic for each
character. Separate actor runners and version validation remain; the strong writer
chooses actions. Set `performance.model_character_proposals=true` to restore model
proposals. Historical beliefs remain explicit when they differ from current canon.
Multi-project routes reserve time for the remaining configured backup attempts,
so a first timeout cannot consume the entire shared deadline. The HTTP attempt
cap and model quality are unchanged.

The scale practice now gives prose routes up to 90 seconds per attempt, sharing
one 180-second writer deadline across three model routes. The former blanket
40-second cap prematurely cut off the second model after the first returned 503.
After both strong Flash routes fail, Flash-Lite can supply a candidate through the
same source, format, literary and factual gates. Review and repair routes also
have this capacity fallback. At most three HTTP requests are allowed per call;
this does not rotate through all keys or change approvals into warnings. If every
provider fails, the workflow preserves diagnostics and remains failed rather than
inventing prose or marking an unreviewed story approved.

Strict draft handoffs now require every expected writing batch to pass the actual
form and length validator. A short candidate gets one complete, source-grounded
expansion attempt with its exact word-range error and a larger output allowance.
Failed expansion retains readable prose for diagnostics but stops the writer and
merge; acceptance independently rechecks form and length. No lowered word target
or provisional approval is substituted.

Pipeline writer packets share identical scene cards, world rules, beat cards and
actor fact references rather than repeating them in serialized direction text.
All current facts, complete authored actor profiles, knowledge allowlists and
historical beliefs remain. Replaying the failed scene-two packet with a 900-word
rejected candidate yields about 51,500 input characters before the system prompt,
within the existing 64,000-character budget. No memory cutoff was increased.

Memory descriptions are required for every kind, including threads; the schema
now requires 1–600 characters and application validation rejects whitespace.
Pipeline extraction can fill a missing description by copying its complete bound
source span only when that span fits. It never truncates evidence or defaults
knowledge holders, outcomes or identity fields. Longer descriptions get one
field-only repair using only the affected records, cited passages and exact
superseded facts. Strong Flash routes precede Lite for that repair, within three
HTTP attempts. All sibling records and non-text fields remain immutable, and the
full evidence/identity validators plus independent factual review still apply.

Failed field repair retains original records and the exact scene for recovery.
Incomplete extraction schedules one explicitly blocked diagnostic check rather
than a matrix of identical failures; no missing verification is treated as a pass.
A replay of the failed live batch recovered all six records with original fields
unchanged; this is a mocked transport regression, not a new live quality result.

A strict short draft with separate paragraphs now uses the existing single repair
slot for source-owned insertions rather than regenerating the entire scene.
The repair aims for the requested target and must reach the allowed minimum; all original
paragraphs stay verbatim, and the exact final exit stays last. The assembled scene
must pass the word range, form and repetition checks before handoff, then still
undergoes literary and factual review. An invalid insertion retains the original
draft for diagnostics, never the raw edit protocol. This adds no rewrite loop or
extra model call beyond the existing writer plus one repair allowance.

The live scale and Iron Man demos now reserve an explicit provider-outage buffer.
If every configured route fails with a transient server/connection error, the
worker checkpoints its exact input and waits before another capacity pass. The
baseline 45-second delay doubles for the next pass, honors Retry-After, and adds
small jitter. Healthy calls do not wait or consume recovery requests. Daily quota,
authentication, configuration and generation-validation faults are not treated as
transient capacity outages.

Each call permits at most three provider passes and nine HTTP attempts including
compatibility requests, with a shared six-minute outage buffer added to its normal
stage deadline. The enclosing job deadline still wins. Inputs and a durable
provider-recovery status remain available when the buffer is exhausted; no missing
story or factual verification becomes approved. The checkpoint supports retrying
the failed job after capacity returns. This is bounded recovery, not an assurance
that an indefinitely unavailable external API can finish a GitHub runner job.

Pipeline memory recovery partitions an invalid extraction into validated sibling
records and invalid records. One bounded repair call patches only the identified
fields of the invalid records: descriptions, knowledge holders, evidence IDs,
belief holders, typed thread/lifecycle metadata, and invalid supersession links.
Multiple structural faults in one record are diagnosed together. Every valid
sibling and unrelated field stays unchanged; the complete result must pass the
original source/cast/type/identity validators and independent factual review.
An event cannot overwrite a resource under a different kind or fact key. A new
source-supported event can instead remain append-only, leaving the prior history
intact; no invented resource balance or witness list is used as a default.

Failed repair preserves the exact source, rejected records and individually
validated partial facts, marked unverified. Partial facts cannot publish canon or
unlock the next scene. Outer-list normalization is lossless, nested malformed
knowledge/link values report validation errors, and malformed wrappers retain the
bounded source re-extraction path. Four saved failing Iron Man outputs replayed
successfully with mocked transport; this is regression evidence, not live approval.

Strict acceptance now blocks unverified memory at the actual handoff gate and
saves prose plus a blocked-handoff report. It cannot report acceptance success and
then fail misleadingly in the following scene’s designer. Literary judgments are
still separate from this factual gate; unverified facts never become canon.
