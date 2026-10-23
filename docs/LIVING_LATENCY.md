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
