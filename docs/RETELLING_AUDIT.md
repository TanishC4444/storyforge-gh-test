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
