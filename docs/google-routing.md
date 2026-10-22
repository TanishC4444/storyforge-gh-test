# Google routing and backup credentials

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
