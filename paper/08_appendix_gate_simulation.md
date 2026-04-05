# Appendix A: Post-Hoc Gate Simulation

To bridge the observational findings of the calibration study and the planned intervention experiment, we apply the introspective behavioral gate post-hoc to all 181 validated Sonnet runs. This simulation measures what the gate *would have done* on the exact trajectories already collected, providing precision and recall estimates without new data collection.

## Gate Design

The introspective gate evaluates each Edit/Write tool call on two criteria derived from Phase 0 passing runs:

1. **Alignment check:** Does the reasoning text preceding the edit mention the target file by name or path? (Binary; threshold = 0.5)
2. **Deliberation check:** Is the reasoning text at least 117 characters? (Median per-call length from passing runs)

If either check fails, the call is flagged as "blocked." Ground truth is operationalized at the run level: a blocked call in a failing run is a true positive.

## Applicability

The gate applies only to Sonnet. Codex never uses Edit or Write tools---it performs all file modifications through Bash commands. This architectural difference means the introspective gate as designed is inherently model-specific, consistent with the broader finding that behavioral features do not transfer across models.

## Results

We evaluate two timing conditions: A1 (gate applied to the first third of the trajectory only) and B1 (gate applied to all calls).

| Condition | Calls Evaluated | Blocked | Block Rate | Precision | Recall |
|-----------|----------------|---------|------------|-----------|--------|
| A1 (early) | 553 | 180 | 32.5% | 0.628 | 0.388 |
| B1 (always) | 553 | 514 | 92.9% | 0.545 | 0.962 |

B1 is impractical: it blocks 93% of all edits. A1 is more selective, blocking roughly one-third of early-trajectory edits with 63% precision---above the 50.8% base failure rate (random blocking precision) but far from deployable.

### Repository Heterogeneity in Gate Performance

Gate precision varies dramatically by repository, mirroring the base-rate differences that necessitated the CWC methodology in the observational study:

| Repository | Edit/Write Calls | Blocked | Precision | Base Fail Rate |
|------------|-----------------|---------|-----------|----------------|
| sympy | 249 | 63 | 0.762 | 58.6% |
| pytest-dev | 118 | 40 | 0.900 | 71.4% |
| django | 138 | 50 | 0.200 | 15.9% |

On sympy (balanced difficulty), A1 achieves 76% precision. On pytest-dev (high failure rate), precision reaches 90%---but this largely reflects the base rate. On django (84% pass rate), precision drops to 20%: the gate flags many edits in runs that ultimately succeed, because django's high pass rate means most runs pass regardless of early reasoning quality.

### Block Reason Analysis

Of 180 blocked calls in A1, 98 were blocked on alignment alone (reasoning did not mention the target file), 1 on deliberation alone, and 81 on both. The alignment check dominates gate behavior. Notably, the alignment check is derived from the reasoning-to-action alignment feature, which was retracted as a standalone predictor ($p = 0.35$ in the within-repo permutation test). This means the primary component of the gate is built on a feature whose observational association did not survive confound control.

## Interpretation

The post-hoc simulation yields three findings relevant to intervention design:

1. **The gate as designed is not deployable.** Precision of 63% overall, with 20% on the highest-volume repository (django), would produce unacceptable false-positive rates in practice.

2. **Repository base rate dominates gate precision.** The same gate that achieves 76% precision on a balanced-difficulty repository drops to 20% on an easy one. Any practical gate must condition on difficulty estimates or repository-specific thresholds.

3. **The retracted feature contaminates the gate.** The alignment check---the gate's primary blocking mechanism---is derived from reasoning-to-action alignment, whose observational association was inflated by between-repo confounding. A revised gate should replace the alignment check with deliberation length (perm $p = 0.0004$) and the deliberation $\times$ diagnostic precision interaction, which survived all statistical tests.

These findings motivate a revised gate design for Phase 1 intervention testing, one that uses the features which survived the full statistical battery rather than those available at the time the gate was initially designed.
