# Troy continuation

`troy-continue.yml` resumes run 39536276390 from its committed `s02_accept` checkpoint. It also requires that run's `s03_design` and `s03_draft` artifacts. It preserves both accepted scenes verbatim and reuses the existing third-scene draft. A mismatched brief or canon checkpoint stops recovery.

For each remaining scene:

1. Use the approved scene card plus latest accepted canon; avoid another independent scene-design generation.
2. Keep independent character contexts. Scene 3 proposals and draft are already available; scene 4 characters still run separately.
3. Draft once, with direction and character proposals included.
4. Split contiguous paragraphs into up to four independently owned editing batches. Each batch sees adjacent paragraphs as read-only context and combines prose, rhetoric and distinct-writing edits in one call.
5. Merge mechanically against the exact source hash. Reject stale results, overlapping ownership, missing batches and paragraph deletion. Editor exceptions preserve original text and produce warnings.
6. Review the final merged prose once for story quality and once for rhetoric, alongside memory extraction. Validate extracted memory afterward. Keep chapter-level review at the end.
7. Commit once. No subsequent prose mutation or extraction/reverification loop. Failed reviews remain explicit provisional warnings; this mode does not claim every issue was repaired.

Deterministic jobs skip inference-runtime installation. Generation jobs retain it. Shorter reviewer instructions keep all required checks and creative/world/plot constraints; role-specific classical craft references still reach planning and writing. Automatic retries are disabled for this continuation, so an unavailable reviewer yields an unverified warning rather than another expensive evaluation. Original worker generation limits remain unchanged.

This removes repeated design, repair, full-scene re-verification and repeated memory extraction. Batching trades additional machines for lower editing latency. CPU generation and the single final chapter audit can still take substantial time; no measured end-to-end speedup is claimed before the live continuation finishes. Persistent idle worker pools and GPU runners are not implemented by this change.

Validation: 64 unit tests, plus an artifact-backed fixture continuation through both remaining scenes. The fixture asserts that the first two accepted entries remain identical and the third-scene draft is reused. Fixture success verifies orchestration and contracts, not live literary quality or performance.
