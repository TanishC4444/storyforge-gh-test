# Cinematic universe expansion with classic runners

This path reuses the separate character runners, scene writer and parallel passage ownership/merge from Actions run **39552359292** (commit `82f0276fea05c3ee43de0c10d41a9780639a6ee8`). That historical workflow completed with provisional literary limitations; its success is not a guarantee of quality.

## Fast start, patient writing

`cinematic-expansion.yml` compiles an explicit author bible, constraints and scene layout without model calls for initial refinement. It preserves the original prompt, marks the plan as proposed, then reconciles the scene against actual canon. It retains the full separate-runner graph: character matrices, direction, writing-beat matrices, independent story/rhetoric/memory branches, paragraph-repair matrices, one final check and strict canon acceptance. The graph supports up to nine scenes per episode; use a matching authored request and scene limit. Larger universes continue across episodes.

The default practice is one developed 900-word Troy scene. Gemini is preferred where configured and falls back to local models; the established Qwen 7B writer remains the local writing route. Writing and review batches have a ten-minute inference cap, bounded by the enclosing job. Invalid or missing reviews still block canon acceptance. Model judgment remains fallible.

Writer, edited and repaired prose is copied into each job's summary and artifact when that stage finishes. The final `readable-story` artifact collects the best available text even if a later reviewer fails. Its status distinguishes unreviewed output from reviewed prose. A rejected or incomplete model response is labeled explicitly. This is stage-level visibility, not token streaming.

Only accepted output creates a `universe-canon` checkpoint. To continue an existing cinematic universe, provide that run through `canon_run` and author a new episode premise/layout. World rules and existing character identities remain stable; new cast IDs may be added explicitly. Source-bound memories and prior episode history survive; author continuity is not automatic character knowledge. The cinematic test uses the current Troy setting, not an invented Marvel continuity.

## Living universe also uses multiple runners

`living-universe.yml` now exposes the full one-event runner graph. It does **not** hide writing and reviews inside one coordinator job or dispatch child workflows. The beginning is compiled quickly, a seeded high-randomness proposal is interpreted by a Gemini-first director, then separate jobs write, review, repair and verify it. The initial proposal is not canon. The default output budget is 900 words for one event, with no predetermined total universe length.

This workflow uses the same six-project Gemini-first routing as cinematic expansion. Qwen models provide bounded fallback for the specific batch that could not be served. It is manually launched/resumed. `resume_run` with the `universe-canon` artifact continues accepted history. After a failed attempt, choosing its `quickstart` artifact preserves prior accepted history and advances the saved random stream without committing the rejected event. Fixture and live checkpoints cannot mix.

The older single-coordinator universe CLI remains available for local experimentation; it is no longer the Actions architecture. Existing runs keep the workflow revision they started with, so a new launch is required to use this graph.

## One final check for editorial disagreements

Classic expansion requests use `execution_policy.editorial_disagreement = one_strict_check`. If a reviewer rejects the edited text, one final adjudicator independently checks all story and rhetoric dimensions against the original prompt, author contract, scoped references, actual chapter, source-bound canon and POV knowledge. Earlier opinions are allegations to verify, not votes. Stylistic preferences remain advisory. This final judgment has zero semantic/format retries; transport failover can still change provider when a provider cannot respond.

The exact final decision is bound to prose, chapter, canon and author requirements. Changed-text verification and the chapter gate reuse it rather than opening another debate. A first disagreement discovered at the chapter gate receives that same one final check. If it passes, the normal independent memory requirements still apply. Mechanical author constraints cannot be waived by model approval.

If the final check fails or is unavailable, the workflow retains a clearly provisional scene and continues without another rewrite/review cycle. Its new facts are withheld from canon; later scenes on that provisional branch also withhold canon updates. The exported manuscript is labeled provisional, and it cannot be imported as an accepted universe checkpoint. Readable drafts remain available even when verification is unresolved. This is forward progress through drafting, not a claim that failed reviews passed.

Already-started Actions runs keep their original code and settings. The policy applies to new launches from the merged revision; it does not silently change an in-flight run.

## Gemini-first paragraph batches and independent projects

Both Actions modes now prefer Gemini. The user confirmed the primary credential and five backups belong to **six distinct Google projects**. These workflows explicitly enable `GEMINI_DISTINCT_PROJECTS=true`: numeric batches start on different anonymous project slots, with separate per-model quota ledgers and circuits. Quota or availability failure can try another project before the local fallback. The legacy credential-only behavior remains the default outside these workflows. Raw credentials and account identifiers never enter prompts or artifacts. Per-runner pacing and inherited reservation deduplication are not a fleet-wide distributed quota lock.

A 900-word scene is allocated into three contiguous writing beats, generated on separate runners and compiled without a full-scene rewrite. Every beat sees the same scene contract, reference mechanisms and canon, plus its own role in the sequence. A rejected beat gets at most one correction confined to that beat. Local fallback is confined to the same batch, with a ten-minute inference cap. No Glitter whole-scene regeneration remains in these Actions paths.

The compiled draft goes directly to review; there is no automatic blanket pre-review humanizer pass. Story and rhetoric dimensions are reviewed in groups of three on independent runners. Their source-bound findings select the affected paragraph IDs. Findings for the same paragraph are grouped, with at most two owned paragraphs per repair batch and read-only neighbors. Gemini checks the allegations against the author prompt and replaces only owned paragraphs needing correction. Unfounded criticism can produce no replacement. Reviewer-proposed replacement text is not applied blindly.

Merging checks ownership, source hashes and duplicates, preserving all untouched prose verbatim. One final strict prompt check follows the merged repairs. Its story and rhetoric decisions are reused without another rewrite loop. Unchanged extracted facts are retained; changed passages trigger source-bound fact extraction. Compact memory verification still controls canon. Missing, invalid or unresolved model output remains explicitly provisional and readable rather than becoming an approval.

The one-scene tests exercise batched writing and paragraph repair, not four separate scenes. The cinematic path supports an authored episode of up to nine scenes. The living-world path keeps randomized event proposals and manual checkpoint resume, but now also uses Gemini first and local models as bounded batch fallbacks.

## Batched memory and continuity

Initial facts are extracted alongside editorial review. Before paragraph repairs, parallel preflight checks each own at most three paragraphs and four extracted facts, with the complete scene available as read-only context. They check fact support, individual knowledge, entrances, custody and causal joins. Source-bound prose findings join the existing paragraph repair plan; extraction findings never trigger prose changes to make an inaccurate memory true.

After repairs, changed evidence refreshes the facts. A second parallel batch matrix verifies the final facts and knowledge holders only, without reopening literary/style disagreements. Every paragraph and fact is assigned once, and joins validate immutable state, prose and fact hashes. Missing or unavailable checks cannot approve canon. One strict final editorial judgment still governs the prose; unresolved output stays provisional and readable.

## Bounded Living universe practice

The same `living-universe.yml` supports one manually resumed event or a four-chapter episode (`scene_limit=4`, one scene per chapter). A request with `performance.living_bounded=true` supplies the explicit episode arc; initial refinement compiles without inference. At each chapter, a fresh saved random proposal is reconciled with actual prior prose and verified canon. The authored arc governs random complications, and the existing character, writing, review, targeted repair and batched memory jobs remain separate runners. Chapters inherit the previous acceptance checkpoint in order. This is bounded operation of the Living universe engine, not the parallel-complete-scenes experiment.

`iliad-2526-living-practice` tests four approximately 700-word chapters of an Iliad opening reimagined in 2526 CE. Its binding future setting replaces the previous Troy smith/gun practice. Fixed carrier identities, distinct captives, nine elapsed days and twelve isolation cartridges reduced by four to eight provide explicit continuity probes. The four-chapter opening ends in withdrawal and a pending petition; the larger war remains unresolved. Fixture checks validate plumbing only. A live model pass remains subject to human assessment of source faithfulness, futuristic specificity and cross-chapter coherence.
