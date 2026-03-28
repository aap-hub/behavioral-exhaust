# Open Questions from Literature (Ranked)

## 1) What uncertainty signal should actually trigger a gate?
- Why it matters: UGA fails if the trigger is uncalibrated proxy confidence.
- Literature partly answering it: Guo et al. (2017), Jiang et al. (2021), Kadavath et al. (2022), conformal prediction work.
- What remains unclear: decision-time calibration for tool-call correctness under long-horizon dependence.
- Experiment/artifact needed: side-by-side comparison of 3-5 gate signals (self-confidence, calibrated probability, conformal set size, critic disagreement, retrieval uncertainty) on identical tasks.

## 2) Where should gates be inserted in the action loop?
- Why it matters: gating every step may cause over-caution overhead; gating too sparsely misses catastrophic actions.
- Literature partly answering it: ReAct, Toolformer, SayCan, selective prediction literature.
- What remains unclear: optimal gate placement policy for coding/web/computer-use traces.
- Experiment/artifact needed: decision-point taxonomy + ablation over insertion points (pre-tool, pre-write, pre-commit, pre-final-answer).

## 3) What is the right objective: minimizing catastrophic failures, expected loss, or coverage-risk?
- Why it matters: different objectives can produce opposite gate-threshold choices.
- Literature partly answering it: Chow reject option, proper scoring rules, selective classification risk-coverage curves.
- What remains unclear: mapping abstract risk-coverage to practical agent cost structure.
- Experiment/artifact needed: explicit utility function for UGA benchmark with costed error categories.

## 4) How do we avoid benchmark gains that are only prompt/protocol overfitting?
- Why it matters: high apparent gains can be invalid if benchmark is gameable.
- Literature partly answering it: Hand (2006), Dynabench (2021), underspecification work, leakage critiques.
- What remains unclear: minimum anti-gaming protocol for small pilot benchmarks.
- Experiment/artifact needed: held-out adversarial task slice + protocol randomization + evaluator blinding where possible.

## 5) How should catastrophic vs severe vs recoverable failures be operationally labeled?
- Why it matters: failure-rate headline is only credible if label contract is consistent.
- Literature partly answering it: Reason (1990), SRE incident practices, reliability taxonomies.
- What remains unclear: inter-rater reliability of labels in agent trace review.
- Experiment/artifact needed: labeling handbook + dual annotation on pilot traces + agreement statistics.

## 6) What is the true overhead frontier of gating?
- Why it matters: intervention is not deployable if reliability gains require large latency/token tax.
- Literature partly answering it: selective prediction tradeoff literature, practical tool-agent papers.
- What remains unclear: stable Pareto frontier in long-horizon coding tasks with repair loops.
- Experiment/artifact needed: threshold sweep with per-task overhead decomposition (decision latency, extra tool calls, escalation cost).

## 7) Can multi-agent disagreement be used as a gate signal without coordination collapse?
- Why it matters: disagreement may improve caution but also induce deadlock and handoff churn.
- Literature partly answering it: shared plans/joint-intention theory, automation teaming challenges, recent multi-agent agent papers.
- What remains unclear: disagreement protocols that improve reliability net of coordination overhead.
- Experiment/artifact needed: 1-agent vs 2-agent critic-ablation with coordination-failure metrics.

## 8) Does UGA generalize across benchmark families or only within one domain?
- Why it matters: Anthropic-facing claim requires transfer beyond one narrow task class.
- Literature partly answering it: SWE-bench/WebArena/OSWorld ecosystem.
- What remains unclear: transfer of tuned gate policy from coding to web/computer-use tasks.
- Experiment/artifact needed: small cross-domain transfer matrix with frozen gate policy.

## 9) How much of UGA novelty remains after accounting for known selective-prediction methods?
- Why it matters: project contribution must be clearly distinguished from prior reject-option literature.
- Literature partly answering it: selective classification, conformal prediction, learning-to-defer.
- What remains unclear: whether UGA contributes a new mechanism, a new benchmark protocol, or just repackaging.
- Experiment/artifact needed: explicit novelty map document (known mechanism vs new operationalization) plus baseline comparisons against non-UGA abstention methods.

## 10) What is the smallest credible pilot that avoids "toy benchmark" criticism?
- Why it matters: scope discipline is required, but too-small pilots lose credibility.
- Literature partly answering it: benchmark methodology and validity literature; HELM-style metric panels.
- What remains unclear: minimum task diversity/sample size needed for defensible directional claims.
- Experiment/artifact needed: pilot power/sensitivity memo with pre-registered stop/go criteria.

## 11) Which failure classes are fundamentally not gate-fixable?
- Why it matters: gating should not be blamed for failures caused by missing capabilities or bad task specs.
- Literature partly answering it: Normal Accidents, human factors and socio-technical failure literature.
- What remains unclear: clean boundary between uncertainty failures and capability failures in agent traces.
- Experiment/artifact needed: postmortem template that forces root-cause class assignment (uncertainty vs capability vs coordination vs spec).

## 12) Which metrics should be primary vs supporting in final claims?
- Why it matters: weak metric hierarchy leads to p-hacking and narrative drift.
- Literature partly answering it: proper scoring rules, classifier-comparison methodology, benchmark-critique literature.
- What remains unclear: best claim stack for UGA (e.g., catastrophic failure first, calibration second, overhead third).
- Experiment/artifact needed: metric hierarchy charter with preregistered claim language and failure conditions.

## Explicit "Do Not Do" from These Questions
- Do not claim reliability improvement from confidence calibration alone.
- Do not publish aggregate success uplift without failure-type decomposition.
- Do not use one benchmark family as universal evidence.
- Do not skip negative-control conditions.
- Do not claim novelty before baseline mapping to selective-prediction literature.

