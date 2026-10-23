# Universe runner graphs

The cinematic and Living universe workflows retain visible character, writing, review, repair and canon jobs in one Actions graph. Their ancestry includes Actions run 39552359292; that historical completion is not a guarantee of literary quality.

## Modes and planning

Cinematic expansion compiles an explicit author episode layout without initial refinement calls. It supports up to nine sequential scenes, with writing beats generated in parallel within each scene. It is separate from the parallel-complete-scenes experiment.

Living universe supports one manually resumed event or an explicitly bounded four-chapter episode. The bounded request sets `performance.living_bounded=true` and supplies its arc. Each chapter reconciles a saved random proposal against actual prior prose and canon; the authored arc governs random complications. Chapters inherit previous acceptance in order. No schedule is installed.

`iliad-2526-living-practice` requests four approximately 700-word chapters of the Iliad opening reimagined in 2526 CE. Fixed ships, distinct captives, custody, elapsed days and a twelve-to-eight cartridge count are continuity probes.

## Memory is the primary source of truth

Full canon, superseded history, fact identities, evidence, uncertainty and individual knowledge holders remain in immutable checkpoints. Summaries never replace them. Context that cannot be safely processed must remain explicitly unverified; it cannot silently become approval.

Extraction covers every actual source paragraph in independent two-paragraph batches. Invalid extraction can receive one focused model correction using its original source, existing canonical identities, rejected output and exact validation error. Missing extraction remains unverified; successfully extracted facts are retained.

Checks partition new facts into groups of at most two and canonical facts, including labeled superseded history, into groups of at most eight. Every new-fact/canon pair is covered; historical states are explicitly labeled so they are not mistaken for current contradictions. If complete coverage would exceed an Actions matrix, the plan fails explicitly and requires a smaller episode or continuation; it never drops facts to fit. Additional source-coverage batches check extraction completeness, not only whether extracted claims are supported. Preflight batches also check continuity; final coverage batches assess memory completeness without reopening prose/style debates. Model packets contain exact relevant prose and complete assigned facts, never shortened fact text or memory summaries. Canon is partitioned rather than truncated.

After editing, unchanged extracted facts are rebound to unchanged source evidence. Changed or memory-flagged passages receive independent re-extraction batches. Failed initial extraction triggers complete source re-extraction rather than permanently inheriting an unavailable result. Every replacement extraction must still pass final source/knowledge checks. Existing canonical history is not deleted by scene editing.

## Summary-assisted story review and exact prose review

Two-paragraph sections receive short model-written summaries carrying source IDs and hashes. Causal story reviewers compare consolidated summaries against the original prompt, author scene contract, current canon and reference applications. Missing summaries cannot approve the review.

Prose reviewers read original passages and their neighbors in smaller sections, with four dimensions per batch. They also assess the corresponding summary's fidelity. Summaries are navigation aids: sentence quality and form are not inferred from a summary. One strict final judgment round checks small dimension groups in parallel against the actual compiled candidate, full current canon, prompt and chapter context. Its six assessments are combined without another model debate. Valid findings survive failures in other review groups.

## Editor authority

Independent faults can be edited in separate small batches. Connected repetition and continuity findings assign linked passages to the same editor, including distant passages. Editors may replace, shorten, restructure, delete or combine owned passages; unaffected source remains untouched. A merge places the combined text under one owned passage and deletes redundant owned passages.

A separate model compares each nonempty proposed edit against the original, findings, original prompt and canon before it is merged. Unavailable or failed assessments retain original text and report uncertainty. Source hashes, disjoint ownership and preservation of readable source are integrity guarantees, not substitutes for literary judgment.

## Models, output and time

Gemini remains preferred. The six credentials belong to six independent projects; `GEMINI_DISTINCT_PROJECTS=true` separates their quotas and circuits and distributes batch starts. Small memory-check batches can try Gemini Flash-Lite after the stronger Gemini routes fail, before CPU fallback; literary editing and final judgment keep the stronger routes. All configured local fallbacks in these presets are Qwen 7B. Glitter and local Gemma 12B remain in older profiles, not this path. Qwen 7B can be slower on CPU; smaller scopes need live performance validation.

Editor and reviewer outputs support readable edit/check lines without JSON grammar, while still accepting compatible structured outputs. Blocking judgments determine aggregate status even when a model's pass header contradicts them. Memory extraction retains a native schema and focused recovery rather than silently accepting malformed updates.

Role-specific elapsed-time allowances cover provider attempts and CPU fallback together. Hosted project-routing attempts are additionally bounded to preserve fallback time. Six-project pacing is still per runner, not a distributed fleet-wide quota scheduler. Additional batches consume additional requests; these changes do not add provider quota or eliminate outages.

## Approval and readable writing

The one-final-judgment policy remains: no endless editorial debate. Missing or unresolved reviews preserve a labeled provisional draft and withhold its facts from canon. Later chapters on a provisional branch also withhold canon updates. Workflow completion, verified writing and canon commitment are distinct outcomes.

Drafts appear in job summaries and artifacts as stages finish. `readable-story` collects the available manuscript even if approval is unresolved. An accepted `universe-canon` checkpoint can resume the same world; `quickstart` can preserve earlier history and random state after a failed event. Fixture and live checkpoints cannot mix. Fixture tests demonstrate orchestration, not literary quality or provider availability.
