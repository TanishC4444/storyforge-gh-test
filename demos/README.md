# Matched continuity demos

Run the **Continuity demos / matched plain LLM comparison** Action manually.
It runs three cases independently with at most two cases in parallel. Each case
compares three short chapters from the same Gemini Flash 3.6 writing model:

- Plain baseline: immutable author brief, rules, initial facts and **all** earlier
  chapters on every call. No deliberate context truncation or planted faulty draft.
- StoryForge components: the same inputs plus production source-bound extraction,
  exhaustive partitioned memory checks and verified draft-branch handoff. One
  editorial assessment can request a targeted paragraph patch; a single strict
  follow-up must pass before that patch is applied.

The cases test private knowledge, resource exhaustion, and irreversible death with
a planted-object payoff. Their five criteria are committed before generation.
Arm order and anonymous manuscript order are reproducibly shuffled. A final model
judge sees A/B labels without method names; every check must cite real chapter and
passage IDs. Source binding validates citations, not the truth of every judgment.
Human assessment is still required before making quality claims.

Each artifact includes both readable stories (including partial drafts), original
scenes, proposed repairs, review outcomes, source-bound memory receipts, timings,
observed token usage and failures. Unknown usage is never treated as zero. Token
counts are a cost proxy, not a dollar estimate. The managed arm has additional
calls: this tests the benefit and cost of that work, not equal compute budgets.
All returned drafts survive downstream failures. A missing memory handoff stops
that arm; an incomplete arm is not awarded a win. No replays or cherry-picked
replacement generations happen automatically.

This is a focused component comparison. It exercises production memory,
source-evidence, ownership, patching and branch-continuity code; it does **not**
replace or certify the full separate-runner Living/Cinematic workflow, RAG,
director, character agents, or long-universe scalability. A tie or a loss is a
valid outcome. Three short scenarios are exploratory demonstrations, not a
statistical evaluation of long-context superiority.

For one local case, after supplying credentials through the environment:

```
python -m scripts.continuity_demo --case secret --out out/secret
```

Each provider operation allows at most two actual HTTP attempts, not a sweep of
the entire key pool. Writers and judges use the same strong model with no CPU or
weaker-model fallback. Memory uses Lite with no CPU fallback. Provider failures
remain visible. The full universe workflows and this demo share the provider
concurrency group to avoid competing runs.
