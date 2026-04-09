# Behavioral Exhaust Mining in Coding Agent Reasoning Traces

Does the unstructured text agents produce while solving tasks contain
extractable signal about whether they'll succeed? Across 373 validated
runs from Claude Sonnet 4.6 and Codex GPT-5.4 on 75 SWE-bench Lite tasks,
this project extracts 24 behavioral features at zero API cost and asks
what survives rigorous confound control.

## The retraction

The original headline finding of this project — that agents which name
the file they're about to edit in their reasoning are more likely to
succeed — survived Bonferroni correction at p = 0.00018. I believed it.
Then I ran a within-repository permutation test (10,000 iterations) and
the effect vanished (p = 0.35). What I had actually measured was that
django, where agents tend to name files explicitly, is also an easy
repository. The whole signal was between-repository difficulty leaking
into a feature that sounded like it was about agent behavior.

The retraction is documented in [PHASE0_MEMO.md](./PHASE0_MEMO.md) and
the commit history. The methodology that caught it — Fisher-combined
within-repo Spearman correlations plus within-repo permutation — is in
[src/analysis.py](./src/analysis.py). I mention this first because
it's the thing I learned from this project that I'd most want a
reviewer to know.

## What survived

- **Structural features transfer across models.** Consecutive error
  streaks and early error rate are the only features significantly
  associated with failure in both Sonnet and Codex within the same
  repository. Nested LOO-CV with held-out tasks: AUC = 0.634 on Codex
  (p < 0.001), 0.569 on Sonnet (p = 0.064, marginal).

- **Linguistic features are model-specific, and one flips polarity.**
  Contrastive markers ("however," "but," "instead") are positively
  associated with success in Sonnet (ρ = +0.282) and negatively in
  Codex (ρ = −0.264) on the same tasks. Any pooled analysis would
  cancel both signals.

- **Internal thinking and external messages carry opposite signal.**
  Tentative language in thinking blocks predicts failure (permutation
  p = 0.0012); expressed self-correction in messages predicts success.
  A pipeline that pools the two layers discards or inverts the signal.

- **Academic hedging is dead for coding agents.** The 209-term Hyland
  hedging vocabulary that works in QA reasoning chains carries zero
  signal here (ρ ≈ 0, p = 0.60). Coding agents express uncertainty
  through structural behavior, not through modal expressions.

- **Signal degrades over the trajectory.** Early and mid-trajectory
  features discriminate pass from fail; late-trajectory features do
  not (ρ ≈ 0, p > 0.6). Any runtime monitoring gate should focus on
  the early trajectory.

## Read the paper

- [paper/paper.md](./paper/paper.md) — full draft, ~11,000 words
- [paper/latex/paper.pdf](./paper/latex/paper.pdf) — typeset version
- [PHASE0_MEMO.md](./PHASE0_MEMO.md) — analysis memo including the
  retraction
- [context/design-decision-trail.md](./context/design-decision-trail.md)
  — ten key methodological choices and why

## Project Structure

```
uga-harness/
├── src/                    # Core pipeline (18 Python modules)
│   ├── runner.py           # Task runner (Claude Code subprocess)
│   ├── codex_runner.py     # Codex task runner
│   ├── trace_collector.py  # Stream-json parser → structured traces
│   ├── feature_definitions.py  # 24 behavioral features, 3 tiers
│   ├── tier2_features.py   # Domain-specific linguistic features
│   ├── analysis.py         # CWC methodology + permutation tests
│   ├── gate.py             # Behavioral gate (introspective + extrospective)
│   ├── gated_runner.py     # Post-hoc gate simulation
│   ├── phase1_protocol.py  # 10-condition gating experiment
│   ├── critic.py           # Cross-model comparison via Codex
│   ├── independent_validate.py  # Fresh-environment edit replay
│   └── db.py               # SQLite schema and operations
├── tests/                  # 6 test suites (86 tests)
├── paper/                  # Research paper + figures
│   ├── paper.md            # Full draft (~11,000 words, 14 tables)
│   ├── latex/              # Typeset LaTeX version (paper.pdf)
│   └── figures/            # 5 publication-quality figures
├── context/                # Research process documentation
│   ├── phase0_final_deliverable.md  # Complete Phase 0 analysis
│   ├── design-decision-trail.md     # 10 key methodological choices
│   ├── dialectic_round*.md          # Internal review rounds
│   └── codex-pipeline-audit*.md     # Codex integration audits
├── tasks/                  # SWE-bench task manifests
├── data/                   # Batch configs, results (DBs excluded — see below)
├── scripts/                # Analysis and task management scripts
├── docker/                 # Validation container
├── PHASE0_MEMO.md          # Phase 0 analysis memo (with retraction)
├── LITERATURE_REVIEW.md    # 42 texts, 13 papers positioned
└── CLAUDE.md               # Project specification
```

## Data

The SQLite databases (~700MB total) containing all 373 validated runs, raw traces, and extracted features are not included in this repository. The canonical database is `data/uga_phase0_complete_final.db`. Contact the author for access.

All analysis can be reproduced from:
- The database (373 runs with full stream-json traces)
- Feature extraction code in `src/feature_definitions.py` and `src/tier2_features.py`
- Analysis code in `src/analysis.py` and `scripts/phase0_analysis.py`

## Quick Start

```bash
# Run a single task (requires claude CLI)
python src/runner.py --task django__django-11179

# Extract features from a trace
python src/feature_definitions.py --db data/uga.db --run-id <run_id>

# Run Phase 1 post-hoc gate simulation
python src/phase1_protocol.py run --condition A1

# Run tests
python -m pytest tests/
```

## Statistical Methodology

The CWC (Confound-Within-Confound) approach controls for repository-level heterogeneity:
1. Compute within-repo Spearman ρ for each major repository separately
2. Verify direction consistency across repos
3. Combine via Fisher's method (χ² = -2∑log(pᵢ), df = 2k)
4. Validate with within-repo permutation test (10,000 permutations)

This methodology caught and enabled the retraction of our own headline finding.

## Dependencies

- Python 3.10+
- `claude` CLI (for running tasks)
- `codex` CLI (for cross-model comparison)
- SQLite 3.35+ (WAL mode)
- Standard scientific Python: numpy, scipy, matplotlib

## Status

- **Phase 0 (Calibration Study):** Complete. 373 validated runs, full analysis.
- **Phase 1 (Gating Experiment):** Post-hoc gate simulation complete (A1/B1 conditions). Intervention testing planned.
- **Paper:** Full draft with LaTeX typeset version.
