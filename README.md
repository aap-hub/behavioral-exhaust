# UGA: Behavioral Exhaust Mining in Coding Agent Reasoning Traces

**What determines the quality of uncertainty signals for agent tool-call decisions?**

This project studies whether structural properties of agent reasoning traces are associated with task success. Across 373 validated runs from two models (Claude Sonnet 4.6, Codex GPT-5.4) on 75 SWE-bench Lite tasks, we extract 24 behavioral features at zero API cost and find that behavioral structure — not linguistic hedging — carries model-specific signal.

## Key Findings

- **Structural features transfer across models**: consecutive error streaks and early error rate are the only features significantly associated with failure in both models
- **Linguistic features are model-specific**: contrastive marker density shows a confirmed polarity flip (positive in Sonnet, negative in Codex within the same repository)
- **Thinking and message layers carry opposite signal**: the word "actually" in internal reasoning correlates with failure (genuine confusion) while in agent messages it correlates with success (performative self-correction)
- **Academic hedging is dead for coding**: the 209-term Hyland hedging vocabulary carries zero signal in either model
- **Signal degrades over trajectory**: early/mid features discriminate pass from fail; late features do not
- **Methodological self-correction**: our original headline finding (reasoning-to-action alignment) was retracted when within-repo permutation testing revealed between-repository confounding

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
