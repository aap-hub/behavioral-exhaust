# UGA Harness

Uncertainty-Gated Autonomy: a research harness that studies whether structural properties of agent reasoning predict tool-call correctness.

## What This Is

A two-phase research project studying behavioral uncertainty signals in coding agents:

**Phase 0 (Calibration Study):** Run coding tasks through Claude Code (Sonnet 4.6), collect traces, extract behavioral features from reasoning text, compare with cross-model behavioral comparison via Codex. Produce a source × trajectory-position interaction matrix characterizing when and where signals are predictive.

**Phase 1 (Gating Experiment):** Build a harness that gates agent tool calls based on Phase 0 findings. Compare gated vs ungated reliability using pass^k and selective risk-coverage metrics.

## Research Question

"What determines the quality of uncertainty signals for agent tool-call decisions?"

Two orthogonal factors:
1. Signal source: introspective (behavioral features from reasoning text) vs extrospective (cross-model comparison via Codex)
2. Trajectory position: does signal quality degrade as the agent's context fills?

## Signal Architecture

**Signal 1 — Behavioral exhaust mining (introspective):** Extract hedging_score, deliberation_length, alternatives_considered, backtrack_count, self_correction_present from the model's reasoning text. Zero API cost. Novel contribution.

**Signal 2 — Cross-model behavioral comparison (extrospective):** Ask Codex "what tool call would you make here?" via `codex exec`. Compare proposed call to agent's actual call. Produces critic_agreement ∈ {full, partial, disagree}.

## Key Constraints

- OAuth-only auth (no Anthropic API key). All measurements via Claude Code or Codex CLI.
- No log-probs (Anthropic doesn't expose them)
- No inline confidence injection (confounds the task)
- Model: Sonnet 4.6 primary, Opus 4.6 Phase 2 extension
- Single labeler with blinded dual-pass protocol

## Context

- Literature corpus: `lit/` directory (42 texts, 8 buckets)
- Anthropic methods synthesis: `context/anthropic-methods-synthesis.md`

## Architecture Principles

- Standalone (no dependency on any specific orchestrator)
- Observable (every decision point logged to JSONL trace schema)
- Configurable (gate strategies are pluggable)
- Grounded in Anthropic's published methodology (clustered SEs, pass^k, power analysis)

## Project Structure (planned)

```
uga-harness/
├── src/
│   ├── runner.py              # Task runner (Claude Code subprocess)
│   ├── trace_collector.py     # Stream-json parser → JSONL traces
│   ├── features.py            # Behavioral feature extractor (§8.2)
│   ├── critic.py              # Cross-model comparison via codex exec (§8.5)
│   ├── labeler.py             # Correctness labeling tool
│   ├── analysis.py            # Calibration analysis pipeline (§8.7)
│   ├── faithfulness_check.py  # Structural faithfulness check (§5.3.1)
│   ├── gate.py                # Behavioral gate strategy (§8.3)
│   ├── gate_critic.py         # Cross-model gate (§8.4)
│   └── anonymize.py           # Trace anonymization (§8.6)
├── tasks/
│   └── manifest.yaml          # Task registry
├── models/
│   └── behavioral_gate.pkl    # Trained logistic regression (Phase 0 → Phase 1)
├── data/
│   ├── uga.db                 # SQLite WAL — all experimental data (raw + features + labels)
│   ├── uga_anonymized.db      # Anonymized export for release
│   └── results/               # Analysis outputs (plots, tables, interaction matrix)
├── tests/                     # Unit + integration tests
├── context/                   # Research context docs
├── lit/                       # Literature corpus
└── CLAUDE.md                  # This file
```

## Commands (to be implemented)

```bash
python src/runner.py --phase 0 --task p0-bugfix-01    # Run single task
python src/features.py --trace data/traces/run-001.jsonl  # Extract features
python src/critic.py --trace data/traces/run-001.jsonl    # Run cross-model comparison
python src/labeler.py --trace data/traces/run-001.jsonl   # Interactive labeling
python src/analysis.py --phase 0                          # Run calibration analysis
python src/gate.py --phase 1 --task p1-bugfix-01          # Run gated task
pytest tests/                                              # Run tests
```
