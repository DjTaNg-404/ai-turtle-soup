# Changelog

## 0.1.0 — 2026-09-22

Initial public source release as `ai-turtle-soup`.

- Separate player history, single-question host context and cumulative affirmative evidence.
- Retain all affirmed originals across the game, including negations, without an eight-turn cutoff.
- Require core-story reconstruction for completion; skip completion inference with no affirmed evidence.
- Report evidence overflow without deleting early clues; preserve pending-question retry.
- Local HTML interface for an API player and selectable Laya / Jev host.
- Puzzle and hidden solution input, without manually defined completion checkpoints.
- Plain-text Chat Completions calls with provider-default generation settings.
- Per-turn answer classification and solution reconstruction assessment.
- Pause, step, retry, replay and export.
- Separate player and host credentials, plus per-turn host provenance.
- Optional Laya dependencies for a lightweight Jev-only installation.
- Pinned checkpoint download helper and offline runtime loading.
- Installation guides, architecture documentation and automated tests.
