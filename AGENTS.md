# Storyforge working instructions

Keep the full, separate-runner Actions graph when the user asks for the full or
massive workflow. Do not substitute the single-coordinator experiment.

The user wants to conserve ChatGPT/Codex account usage while we work. Keep
responses concise, avoid repeated discovery or unchanged polling, batch independent
reads, and run meaningful checks once per change. Do not introduce recurring
account-usage polling or per-turn snapshots unless explicitly requested. The
existing local account snapshot is account-wide and cannot be attributed to this
chat. Keep account IDs and credentials out of repository files.
