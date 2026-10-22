# Cinematic universe expansion with classic runners

This path reuses the separate character runners, scene writer and parallel passage ownership/merge from Actions run **39552359292** (commit `82f0276fea05c3ee43de0c10d41a9780639a6ee8`). That historical workflow completed with provisional literary limitations; its success is not a guarantee of quality.

## Fast start, patient writing

`cinematic-expansion.yml` compiles an explicit author bible, constraints and scene layout without model calls for initial refinement. It preserves the original prompt, marks the plan as proposed, then reconciles the scene against actual canon. It retains the full separate-runner graph: character matrices, direction, writing, passage-editor matrices, independent story/rhetoric/memory branches, repair, fresh verification and strict acceptance. The graph supports up to nine scenes per episode; use a matching authored request and scene limit. Larger universes continue across episodes.

The default practice is one developed 900-word Troy scene. Gemini is preferred where configured and falls back to local models; the established Qwen 7B writer remains the local writing route. Reviewer calls have an explicit 30-minute budget in these workflows, bounded by the enclosing job, rather than the shorter default. Invalid or missing reviews still block canon acceptance. Model judgment remains fallible.

Writer, edited and repaired prose is copied into each job's summary and artifact when that stage finishes. The final `readable-story` artifact collects the best available text even if a later reviewer fails. Its status distinguishes unreviewed output from reviewed prose. A rejected or incomplete model response is labeled explicitly. This is stage-level visibility, not token streaming.

Only accepted output creates a `universe-canon` checkpoint. To continue an existing cinematic universe, provide that run through `canon_run` and author a new episode premise/layout. World rules and existing character identities remain stable; new cast IDs may be added explicitly. Source-bound memories and prior episode history survive; author continuity is not automatic character knowledge. The cinematic test uses the current Troy setting, not an invented Marvel continuity.

## Living universe also uses multiple runners

`living-universe.yml` now exposes the full one-event runner graph. It does **not** hide writing and reviews inside one coordinator job or dispatch child workflows. The beginning is compiled quickly, a seeded high-randomness proposal is interpreted by a local director, then separate jobs write, edit and verify it. The initial proposal is not canon. The default output budget is 900 words for one event, with no predetermined total universe length.

This workflow has no Gemini credentials. Glitter 12B writes; Qwen models perform planning, passage editing and review. It is manually launched/resumed. `resume_run` with the `universe-canon` artifact continues accepted history. After a failed attempt, choosing its `quickstart` artifact preserves prior accepted history and advances the saved random stream without committing the rejected event. Fixture and live checkpoints cannot mix.

The older single-coordinator universe CLI remains available for local experimentation; it is no longer the Actions architecture. Existing runs keep the workflow revision they started with, so a new launch is required to use this graph.

## One final check for editorial disagreements

Classic expansion requests use `execution_policy.editorial_disagreement = one_strict_check`. If a reviewer rejects the edited text, one final adjudicator independently checks all story and rhetoric dimensions against the original prompt, author contract, scoped references, actual chapter, source-bound canon and POV knowledge. Earlier opinions are allegations to verify, not votes. Stylistic preferences remain advisory. This final judgment has zero semantic/format retries; transport failover can still change provider when a provider cannot respond.

The exact final decision is bound to prose, chapter, canon and author requirements. Changed-text verification and the chapter gate reuse it rather than opening another debate. A first disagreement discovered at the chapter gate receives that same one final check. If it passes, the normal independent memory requirements still apply. Mechanical author constraints cannot be waived by model approval.

If the final check fails or is unavailable, the workflow retains a clearly provisional scene and continues without another rewrite/review cycle. Its new facts are withheld from canon; later scenes on that provisional branch also withhold canon updates. The exported manuscript is labeled provisional, and it cannot be imported as an accepted universe checkpoint. Readable drafts remain available even when verification is unresolved. This is forward progress through drafting, not a claim that failed reviews passed.

Already-started Actions runs keep their original code and settings. The policy applies to new launches from the merged revision; it does not silently change an in-flight run.
