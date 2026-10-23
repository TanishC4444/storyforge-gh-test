# Google routing and backup credentials

## Current adaptive universe practices

The repository secret now holds 18 backup credentials alongside the unchanged
primary secret: 19 configured slots. This is configuration, not proof that every
slot has active model quota or belongs to a distinct project. Keep the primary
and existing five backups in their original order when extending the pool so
inherited per-slot quota records retain their meaning. Never put credentials in
source files, artifacts, or diagnostic output.

The adaptive practice settings supersede the older routing examples below.
Independent jobs and numeric batches spread their starting slots across the
configured pool with `GEMINI_DISTINCT_PROJECTS=true`. That setting assumes
independent projects; additional keys for the same project do not add quota.
Each model call still permits at most two actual HTTP requests across its routes;
adding credentials does not cause a 19-key retry sweep. Required literary roles
stop explicitly if hosted quality is unavailable rather than silently switching
to slow CPU prose generation.

Short scenes are written continuously. Independent prose checks combine their
dimensions into coherent paragraph windows; memory verification still checks
every required source/history partition. The separate-runner graph remains
visible, with editorial matrices capped at two concurrent jobs and memory
matrices at three. Living and cinematic runs share a provider concurrency group.
Dependent scene handoffs wait for verified factual memory. These limits keep
parallelism useful without multiplying requests indiscriminately; they are not
a distributed project-quota lock or a measured latency guarantee.

Actions reads the existing `GEMINI_API_KEY` primary and the encrypted
`GEMINI_API_KEYS` secret (a JSON array of backup strings). The client deduplicates
credentials, advances after authentication/permission failure or Google's explicit
API_KEY_INVALID reason, and remembers a working credential within the process.
Credentials never enter packets, usage records, fixtures, or provider diagnostics.
Other HTTP 400 errors do not rotate credentials.

The practice and full parallel examples enable `execution_policy.model_routing:
quality`. Writers, beat writers and global repairs use Gemini 3.8 Flash; structural
editing and chapter audits use Gemini 3.6 Flash. Other structured development,
refinement, scene planning, character work, memory extraction, routine review and
line editing use Gemini 3.5 Flash Lite. Memory verification keeps an independent
Gemma 4 31B route. Existing POV, canon, evidence, scope, prose form and length
validators still apply. The legacy CPU policy remains available by omitting this
profile and the hosted_prose setting.

Each route has one alternate model: 3.8 ↔ 3.6; Lite → 3.6; Gemma → Lite.
After hosted routes fail, required work retains the existing CPU fallback. Optional
editing retains the last validated prose with an explicit review-required report
instead of spending minutes rewriting it on CPU. These choices balance quality and
latency; they are not a measured guarantee of literary quality.

Google limits quota per project, not per API key. A 429 never rotates credentials
and never triggers an immediate generation retry. The failed model opens a
cooldown (Retry-After when numeric, otherwise 60 seconds); explicit daily quota
violations pause that model until midnight Pacific. Other models may have quota
available. A key from another project may have different limits, but capacity is
not assumed or multiplied by the number of keys.

Conservative local limits (RPM / token reservation per minute / run calls):

| Model | Limits |
| --- | --- |
| 3.8 Flash | 4 / 220,000 / 18 (one reserved for final audit) |
| 3.6 Flash | 4 / 220,000 / 18 |
| 3.5 Flash Lite | 12 / 220,000 / 450 |
| Gemma 4 31B | 24 / 14,000 / 120 |

Token reservations include the requested output ceiling. These are run safety
budgets, not a claim that daily capacity is available. Quota reservations are locked
within a runner and inherited from upstream artifacts without double counting.
Independent runners are not protected by a distributed lock: simultaneous jobs
and other applications can still cause project-wide 429s. The full separate-runner
workflow graph is retained. Google AI Studio is the authority for remaining quota;
the supplied 28-day peak chart is not a remaining-capacity counter.

References: https://ai.google.dev/gemini-api/docs/rate-limits and
https://ai.google.dev/gemini-api/docs/models .

## Literary quality mode

The practice and full parallel examples now additionally enable
`execution_policy.literary_quality`. This supersedes the fast routing above:
writers use 3.8 Flash → 3.6 Flash → hosted Gemma 31B before CPU Glitter 12B.
Editing and literary reviews use Flash 3.6/3.8 and Gemma 31B, with Gemma 4 12B
as the CPU fallback; creative/critical roles do not downgrade to Flash Lite or
Qwen 3B. Routine structured preparation may still use Lite. One attempt per hosted
model hands transport failures to the next route; provider circuits and quota
budgets still apply.

The author writing brief is injected into hosted and CPU creative calls, and
`style_fidelity` is an evidence-backed rhetoric dimension. The requested style
comes from the input, so epic prose is not imposed on other genres. Passing these
checks is evidence of compliance, not a guarantee of matching a historical author's
literary achievement. Findings retain their original negative judgments; passage
IDs determine paragraph locations in application code. Scene-wide findings remain
scene-wide, and unknown evidence is rejected.

Known model-specific project cooldowns are excluded before choosing the bounded
project attempts. This inspects local health records without an HTTP request;
unknown projects still obey the same attempt cap, and other models are unaffected.
Cooldowns are inherited only where the caller supplies upstream quota artifacts;
this does not create a distributed cross-run health service.
