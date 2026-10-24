# Sequential story stress suite

Run **Sequential story stress suite** from Actions. It dispatches the established
full separate-runner living pipeline, waits for its terminal state, collects its
audit and readable-story artifacts, and only then starts the next case. It does
not replace the writing/review graph with a coordinator inference call.

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
four-scene participant layout. Scene length remains 80–130% of the target, not
an exact-word or page-count guarantee.

The author supplies conflict and dramatic function but deliberately does not
specify the culprit, discovery or decisive twist. The model must plant and pay
off evidence, change leverage and retain costs. The continuation imports only a
fully approved canon checkpoint and asks for consequences, not the same opening.
If its parent fails, it is recorded as blocked rather than restarted from empty
memory. Independent cases continue after ordinary child failures.

## Provider policy

The suite requires the existing 45-second exponential Gemini outage backoff,
three bounded rounds and a maximum nine HTTP attempts per role call. Respect
Retry-After; actual cooldown may be longer. All hosted roles remain hosted-only:
there is no silent or immediate local-model downgrade. Daily exhaustion, auth
errors and invalid output are not mistaken for temporary capacity; inputs and
partial drafts stay available instead of manufacturing approval. Sustained daily
exhaustion may require a later rerun after reset.

## Reports and limits

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
