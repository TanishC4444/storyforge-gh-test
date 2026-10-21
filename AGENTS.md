# Storyforge working instructions

Keep the full, separate-runner Actions graph when the user asks for the full or
massive workflow. Do not substitute the single-coordinator experiment.

The user wants ChatGPT/Codex account usage recorded while discussing this project.
When the account-usage tool is available, sample the account-wide limits near the
start and end of a work turn and append sanitized timestamped snapshots to
reports/chat-usage/account-usage.jsonl. Keep that directory local and excluded from
Git. Record window length, used percentage and reset time; omit account IDs and
credentials. Never attribute account-wide changes solely to this chat or invent
per-chat token counts. These records differ from story-model API usage reports.
