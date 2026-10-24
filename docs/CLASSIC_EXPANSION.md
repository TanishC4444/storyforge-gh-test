# Universe runner graphs

Generated YAML shares common nonsecret environment values and reuses exact step/config mappings through YAML anchors and aliases. Secret values stay on task steps. This reduces parser configuration size while preserving every job and dependency.

The cinematic and Living universe workflows retain visible character, writing, review, repair and canon jobs in one Actions graph. Their ancestry includes Actions run 39552359292; that historical completion is not a guarantee of literary quality.

## Modes and planning

Cinematic expansion compiles an explicit author episode layout without initial refinement calls. It supports up to nine sequential scenes, with coherent writing batches and parallel factual/editorial processing. It is separate from the parallel-complete-scenes experiment.

Living universe supports one manually resumed event or an explicitly bounded two- or four-chapter episode. The bounded request sets `performance.living_bounded=true` and supplies its arc. Each chapter reconciles a saved random proposal against the full current memory bridge; the authored arc governs random complications. Chapters inherit previous acceptance in order. No schedule is installed.

`iliad-2526-living-practice` requests four approximately 700-word chapters of the Iliad opening reimagined in 2526 CE. Fixed ships, distinct captives, custody, elapsed days and a twelve-to-eight cartridge count are continuity probes.

## Memory is the primary source of truth

Full canon, superseded history, fact identities, evidence, uncertainty and individual knowledge holders remain in immutable checkpoints. Summaries never replace them. Context that cannot be safely processed must remain explicitly unverified; it cannot silently become approval.

The current universe presets use coherent source windows: approximately 350 words per extraction batch and 450 words per continuity-coverage window. This is a processing division, not a memory summary. Extraction retains all material changes, identities, ownership, private knowledge and supporting evidence. Invalid extraction can receive one focused correction; missing extraction remains unverified.

Verification checks groups of up to eight new facts against partitions of up to twenty historical facts, covering every new-fact/history pair. Superseded states are labeled. Source-coverage checks also test extraction completeness and preflight continuity. If complete coverage exceeds the Actions matrix or context capacity, the run stops explicitly rather than discarding facts.

After editing, unchanged source-bound facts are retained and changed or memory-flagged source is re-extracted. A passing factual preflight can be reused only when state, prose and extracted-memory hashes are identical. Changed source, changed facts or a failed/unavailable proof requires fresh checking. Memory issues cite existing passage IDs; the application resolves exact source quotations instead of trusting model-written quotes.

A literary outage does not erase an independently verified factual handoff. Those facts are stored in a separate, explicitly provisional `draft_memories` ledger, with exact-source verification receipts, stable IDs and individual knowledge holders. They may connect subsequent draft scenes, but they are not promoted to approved universe canon. If the previous scene has neither committed canon nor a verified draft-memory receipt, generation stops before spending tokens on the next scene. Published canon, source-verified draft continuity and unverified allegations are distinct.

## Coherent writing and review batches

Scenes up to 1,500 target words are written continuously in one batch under adaptive batching. Longer scene budgets use larger bounded writing units with concrete handoffs. Each writer gets the original author contract and full current continuity, rather than an automatically rewritten initial prompt.

Prose review windows are approximately 650 words. All eight prose dimensions are checked together; one story review reads the actual scene across all nine causal dimensions. A final scene up to 1,000 actual words is read as one complete unit, so repeated dialogue, reenacted revelations, tense drift, inventory errors and planning-language leakage cannot hide between tiny review windows. Longer final scenes use coherent passage windows plus a global causal check. Exact repeated-dialogue candidates are supplied as evidence for contextual judgment, never as an automatic literary score.

Unchanged passing story/prose assessments can be reused with exact-source validation. Edited text, failed judgments or incomplete judgments require the one strict final round. A final round is never an automatic approval. Source-linked summaries remain navigation aids, not fact memory or substitutes for actual prose review.

Editorial assessments use the native schema. A returned malformed assessment can receive one bounded clarification with existing verdicts frozen; missing issues/checks cannot be resolved by flipping failure to approval or dropping blocking findings. Unavailable responses are not repeatedly resubmitted. Final diagnostics retain specific batch errors and valid findings instead of replacing them with a generic unavailable message.

## Editor authority

Independent faults can be edited in separate small batches. Connected repetition and continuity findings assign linked passages to the same editor, including distant passages. Editors may replace, shorten, restructure, delete or combine owned passages; unaffected source remains untouched. A merge places the combined text under one owned passage and deletes redundant owned passages.

A separate model compares each nonempty proposed edit against the original, findings, original prompt and canon before it is merged. Unavailable or failed assessments retain original text and report uncertainty. Source hashes, disjoint ownership and preservation of readable source are integrity guarantees, not substitutes for literary judgment.

## Medium and creative freedom

The application selects `book` (novel), `short_story`, `stage_play`, `screenplay`, `audio_drama`, or `comic_script` without inference. An explicit medium overrides automatic prompt detection. The same format contract reaches writers, editors and reviewers: scripts retain speaker cues, performable directions and appropriate scene/panel headings. Only the first writing batch opens the scene. The scene designer supplies concrete per-batch entry/action/exit contracts within its existing call; parallel writers share the complete proposed handoff rather than guessing at neighboring outcomes.

Scene designers, writers and character workers use full current canonical facts, with separate visibility-filtered actor memory. Current universe graphs connect scenes through this memory rather than rereading prior story excerpts as their main bridge. All evidence and superseded history remain in checkpoints and exhaustive partitioned checks. An oversized context or matrix is an explicit capacity failure, never silent memory truncation.

Opt-in `creative_freedom` config controls intensity, new cast, character deaths, resurrection, protected identities, per-scene additions and a maximum cast of 32. Seeded shock proposals include betrayals, catastrophic success, faction splits, conspiracies and apparently conflicting evidence. The director chooses connected complications, plants clues before payoffs, and carries fallout into subsequent scenes. Intensity is not a death quota or a promise of literary quality. Author rules and established consequences govern random draws.

Generated character profiles remain proposals until their scene is accepted, preserve immutable IDs and resume with the universe. Evidence-bound lifecycle records distinguish alive, dead, missing and unknown; a confirmed death cannot silently become alive/unknown/missing. Thread records preserve seeded, escalating, payoff and closed states under stable identities. Models must extract the actual events and knowledge holders; a random draw or planned death cannot enter canon by itself. A protected-character death is not accepted. A permitted POV replacement after death requires `flexible_pov=true`; otherwise the explicit author POV remains binding.

Two short live practice briefs exercise different formats and graphs: `chaos-novel-practice` runs two Living chapters, while `stage-play-practice` runs two cinematic scenes. Both target approximately 1,000 total words. Transport fixtures exercise their full review/repair/memory/acceptance paths; live results remain a separate quality and latency measurement.

## Models, output and time

The six credentials belong to six independent projects. Current universe presets reserve Flash for writing/editing, use Flash 3.6 for literary review, and use Flash-Lite for routine memory, planning and verdict clarification. Reviewers no longer cascade through the writer's preferred route. Writers, substantive editors and literary reviewers require hosted capacity rather than silently accepting the Qwen 7B CPU degradation observed in the failed practice. Legacy local profiles remain available separately.

Each model call has a shared cap of two actual HTTP attempts across project/model failovers, including compatibility retries. A single-model call may try two project slots; a two-model call allocates one slot to each model route. Small packets use a conservative byte-based token reservation, avoiding a separate countTokens request. The six-key pool remains available; a call does not exhaustively probe it. One malformed returned artifact may have a distinct bounded clarification; transport failures do not cause an empty writing retry.

Memory/extraction matrices use at most three concurrent workers; editorial matrices use at most two. The two universe workflows share a concurrency group so their runs do not simultaneously contend for the same free-tier capacity. This is conservative scheduling, not a distributed quota broker for every historical workflow or external API consumer. Provider quotas and outages still exist; unavailable capacity is reported rather than converted into approval.

Time allowances are bounded per role, with short hosted-route deadlines. The provider smoke uses at most three tiny HTTP attempts total, one per configured route, with 12-second request limits. It is a capacity check, not a writing benchmark.

The 584-word chapter from run 39897042290 demonstrates the allocation change without new inference: initial prose reviews 14 to 1, story reviews 3 to 1, final reviews 17 to 1, and preflight memory checks 13 to 4. All twelve extracted facts and complete historical evidence remain represented. This measures planned work reduction; live latency and literary quality must be measured independently.

## Approval and readable writing

The one-final-judgment policy remains: no endless editorial debate. Missing or unresolved reviews preserve a labeled provisional draft and withhold its facts from canon. Later chapters on a provisional branch also withhold published-canon updates while retaining independently verified draft continuity. Workflow completion, verified writing and canon commitment are distinct outcomes.

Drafts appear in job summaries and artifacts as stages finish. `readable-story` collects the available manuscript even if approval is unresolved. An accepted `universe-canon` checkpoint can resume the same world; `quickstart` can preserve earlier history and random state after a failed event. Fixture and live checkpoints cannot mix. Fixture tests demonstrate orchestration, not literary quality or provider availability.

### Sequential nonlinear stories and foreshadowing

Use **Living universe / verified-memory pipeline** with scene designs in reading
order. Give each scene an explicit `time`, `setting`, and dramatic task; use
`restrictions` to identify what must remain unknown or unresolved. For a flashback,
state the earlier event time explicitly and mark the return to the present. The
`hard-chronology` brief demonstrates four scenes with a flashback and a climax.

The designer, writer and reviewers receive the authored reading-order/time map.
They must distinguish reader knowledge from character knowledge, and historical
state from present state. Source-bound thread records retain their stable identity
through setup, escalation and payoff, with exact earlier passage evidence when
available. These instructions share the existing calls; they add no review round
and do not shorten the full memory ledger. They guide model judgment rather than
providing a complete automatic temporal reasoning engine.

For a failed episode, `fresh_run` imports its approved prefix and saved unfinished
drafts into a new run. Artifact fetching traverses every GitHub listing page,
including checkpoints older than the first 100 artifacts. Finished scenes keep
their original evidence; unfinished drafts receive fresh checks. Formatting-only
normalization can supply a missing suggestion on an otherwise complete advisory;
blocking findings and invalid citations still prevent acceptance.
