# Full Silent Bell live test

Launched 20 October 2026 using examples/silent-bell-full.json and the balanced model profile.

- Coordinator: https://github.com/TanishC4444/storyforge-gh-test/actions/runs/39384520129
- Initial refinement runner: https://github.com/TanishC4444/storyforge-inference-runner/actions/runs/39384565662
- Target: three chapters, three scenes per chapter, about 850 words per scene.
- Initial refinement is a separate model call, before chapter planning.
- Local preflight: 12 deterministic/adapter tests passed.
- The live test was still running when this launch record was written. This document does not assert that chapters were generated or quality checks passed. Actions is authoritative for current execution status.

The coordinator saves scoped input packets, outputs, reviews, and accepted state. Its final artifact is uploaded on success or failure. If interrupted, use the saved artifact's run ID as resume_run_id in the Story coordinator workflow, keeping backend=github.
