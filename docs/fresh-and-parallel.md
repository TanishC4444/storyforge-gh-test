# Fresh recovery and simultaneous-scene trial

The full Living pipeline remains the default separate-runner graph. Its optional
`fresh_run` input imports the same episode from a failed full-pipeline run into a
new run, rather than starting a new universe episode. The author brief, original
cast and initial facts must match. An approved, source-bound prefix is retained;
its jobs are skipped and its original proof artifacts are retained for auditing.
Unfinished drafts are imported without approval and receive fresh reviews and
memory extraction against the current canonical history. Previously unverified
draft memory is not promoted. A fresh run can itself be a later recovery source.

The harder suite's nonlinear case uses a fresh workflow run after failure.
**Fresh recovery and simultaneous-scene comparison** also starts a recovery trial
from a selected nonlinear source run and waits for completion. If incomplete,
it waits 90 seconds and starts one more new run from the new checkpoint. This
is a bounded demonstration, not an unlimited quota retry loop.

Retry fixes include:

- Surplus matrix artifacts from a different plan hash are ignored; absent current
  evidence still blocks approval, and conflicting duplicates in the current plan
  still fail validation.
- Acceptance stores the exact consumed state, text binding, facts and factual
  proof. The audit does not select an unrelated old recovery folder merely because
  it exists.
- An exact existing character ID/name returned under new characters is normalized
  to the registered identity, without replacing its profile. Ambiguous collisions
  remain errors.
- Exhaustion of an HTTP request round can enter the bounded outage backoff,
  instead of obscuring earlier transient provider errors.

## Separate parallel experiment

**Deep planning / simultaneous scenes** uses a different implementation:

1. Compile the author brief, full initial memory and reading order.
2. Develop one detailed global board with explicit entry/exit states, action beats,
   knowledge acquisitions, custody, numbered resources, arrivals, event time,
   planted clues/payoffs and non-repetition constraints.
3. Refine each scene description concurrently, then reconcile the entire board.
4. Write three or four complete scenes concurrently on separate runners.
5. Extract source-bound facts and review each actual scene concurrently. Audit
   the complete actual manuscript for global handoffs and continuity. Planned
   states never count as evidence that events happened.
6. Patch affected scenes concurrently, refreshing their memory and reviews.
7. Perform a final manuscript audit; export canon only on approval. Always retain
   readable drafts, including when a scene or provider fails.

This pilot uses its own seven-dimension source-bound audit, not the full Living
literary rubric. Timing reports must identify this difference. The recovery trial
also reuses prose, whereas the parallel experiment writes from scratch: their
wall times are useful operational measurements, not a controlled speedup claim.
Synthetic fixture tests validate transport only and are marked as such.

Both trials use the same four-scene nonlinear brief by default. The comparison
workflow waits for both and saves each child run URL, elapsed time, real approval
status and available story text. Its completion status is separate from quality
approval.
