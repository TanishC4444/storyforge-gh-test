# Focused stress testing

The default strategy is risk based. Do not launch a Cartesian product of paid
generation requests. Reuse historical Actions artifacts, inspect their actual
approval audits, and rerun only a changed or historically unreliable boundary.
An Actions queue completing successfully is distinct from manuscript approval.

## Default offline check

```powershell
$env:PYTHONUTF8 = '1'
python -m scripts.combinatorial_stress
```

Seven representative cases cover every individual genre, format, scene-count,
word-target, cast-size and complexity level, including a combined upper boundary
of four scenes, 1,600 words per scene and 32 characters. They execute the actual
Living workflow's separate stages, matrix expansions and artifact manifests in
isolated directories. Fixture responses establish orchestration and evidence
contracts; they do not establish model writing quality, genre fidelity or length.

For a localized fix, run only its case (`--case 6` selects the combined upper
boundary). The normal Tests workflow already runs the broad unit regression
suite; the targeted stress workflow adds the relevant stress and adapter checks.

## Optional wider coverage

```powershell
python -m scripts.combinatorial_stress --coverage pairwise
python -m scripts.combinatorial_stress --grid-only --exhaustive-contracts
```

The seeded pairwise selection covers every pair of input values in 36 graph
executions. Exhaustive *input-contract* validation checks 6,480 combinations and
does not call models. Neither is the default. The saved manifest reports exactly
which combinations and pairs were selected; representative coverage is never
labeled complete pairwise coverage.

## Live acceptance

In Actions, select **Targeted story stress and live acceptance** on the test
branch. Live runs are off by default. Enable `live` explicitly and choose only
the needed `live_cases`:

| ID | Intended check |
|---|---|
| matrix-01 | One-character, one-scene, 100-word mystery baseline |
| matrix-02 | Two-scene fantasy screenplay; continuity and 16 initial facts |
| matrix-03 | 800-word science-fiction audio drama with dense memory; length regression |
| matrix-04 | Two-scene romance stage play with a 16-character cast |
| matrix-05 | Four-scene historical comic with a 32-character cast |
| matrix-06 | Two-scene horror prose with a 1,600-word target |

The targeted live selection defaults to the first three cases; select only
`matrix-03` when investigating the observed audio-length failure. Cases are
sequential, each is capped at 20 minutes, and automatic scene retries are off.
They dispatch the existing full runner graph, preserving its independent role
jobs. Credentials remain in Actions secrets and never enter generated briefs.

A live pass requires job success, the full requested scene count, per-scene
approval, final-text evidence binding, preservation of initial facts, the correct
cast size, and the requested word range. Failed or short drafts remain available
for inspection and cannot become accepted canon. Literary merit remains a
separate human assessment.

## Local Windows verification

Run the Studio with `python -X utf8 -m storyforge.studio`. The launcher uses a
selector event loop and h11 on Windows after concurrent TCP tests exposed stalls
with the default network stack. Ledger locking supports both Unix and Windows. Keep
transport-level load results separate from in-process API checks.
