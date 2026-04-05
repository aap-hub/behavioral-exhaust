# Anthropic Research Methods Synthesis for UGA

Compiled 2026-03-28 from deep reading of 17+ Anthropic publications.
Use this to ground UGA's methodology in Anthropic's own practices.

## Statistical Methods Anthropic Uses

### From "A Statistical Approach to Model Evaluations"
- Clustered standard errors on unit of randomization (can be 3x naive SEM)
- Paired-differences tests (not two-sample) when question lists shared across models
- Power analysis BEFORE running evals
- 95% CI = mean +/- (1.96 x SEM)
- For CoT non-determinism: resample and average across runs
- Correlation of question scores between frontier models: 0.3-0.7 (free variance reduction)

### From tau-bench (Yao et al., arXiv:2406.12045)
- pass^k = p^k (probability ALL k runs succeed)
- Ground truth: database end-state comparison (objective, automated)
- Non-determinism: re-run with lexical variation, user simulator produces diverse utterances
- Error taxonomy: goal_partially_completed, used_wrong_tool, used_wrong_tool_argument, took_unintended_action

### From Bloom (Automated Behavioral Evaluations)
- 100 rollouts x 3 repetitions per behavior per model (Monte Carlo)
- Judge model: Claude Opus 4.1, Spearman 0.86 with human labels
- Validation: discrimination between model organisms vs baseline (9/10 success)
- Elicitation rate = fraction of rollouts scoring >= 7/10

### From Alignment Faking Revisited
- Thresholded multi-vote classification: N=20 votes at temperature 1
- AUROC improved from 0.62 to 0.92 with this method
- ~100 hand-labeled examples as ground truth

## Key Faithfulness Findings (Direct UGA Implications)

### From "Reasoning Models Don't Always Say What They Think" (Chen et al. 2025)
- CoT faithfulness score = E[1[c_h verbalizes hint] | a_u != h, a_h = h]
- Score is an UPPER BOUND on true faithfulness
- Claude 3.7 Sonnet: 25% faithfulness. DeepSeek R1: 39%.
- Unfaithful CoTs are LONGER than faithful ones (2064 vs 1439 tokens for Claude)
- Reward hacking: >99% exploitation but <2% verbalization
- RL improves faithfulness initially (63%) but plateaus (28%)
- NO formal hypothesis tests — relies on descriptive statistics + error bars

### From "Measuring Faithfulness in CoT" (Lanham et al. 2023)
- Four perturbation experiments: early answering, adding mistakes, filler tokens, paraphrasing
- Summary metric: Area Over Curve (AOC) — higher = more faithful
- Defense-in-depth: each test rules out one class of faithfulness failure
- Key finding: faithfulness DEGRADES with model size (inverse scaling)
- 100 samples per question per condition, nucleus p=0.95, temp=0.8
- NO formal significance testing

### Implication for UGA Behavioral Features
The faithfulness papers consistently find:
1. Content faithfulness is poor and degrades with scale
2. But STRUCTURAL properties (CoT length, elaborateness) correlate with faithfulness state
3. Unfaithful CoTs are systematically longer — this IS a structural signal
4. Neither paper uses formal hypothesis tests — they rely on descriptive statistics + visual trends
5. This sets the bar for UGA: descriptive statistics with error bars is Anthropic-standard

## Ground Truth Approaches Used Across Anthropic Research

| Paper | Ground Truth | Method |
|-------|-------------|--------|
| Alignment faking | Researcher-created system prompts | Known by construction |
| Auditing agents | Researcher-implanted behaviors | Known by construction |
| Bloom | No external ground truth | Validated via human correlation + model organism discrimination |
| tau-bench | Database end-state | Objective automated comparison |
| BrowseComp | Post-hoc manual verification | Answer source tracing |
| Faithfulness | Paired hint/no-hint comparison | Causal inference from intervention |
| UGA (ours) | validation_command exits 0 | Deterministic automated check |

UGA's ground truth (validation_command) is closest to tau-bench's approach.

## Novel Measurement Innovations from Anthropic

1. Super-agent aggregation: parallel agents from identical states, aggregate findings
2. pass^k metric: exponential reliability decay
3. Bloom's agentic eval generation: automated scenario + rollout + judgment
4. Thresholded multi-vote classification (N=20 votes, AUROC 0.62 → 0.92)
5. Inter-agent web contamination detection
6. Eval awareness behavioral fingerprinting (exhaustion-pivot-hypothesis pattern)

## What UGA Adds That Anthropic Hasn't Done

1. Nobody has mapped behavioral STRUCTURAL features to tool-call correctness
2. Nobody has tested whether structural features resist the faithfulness problem
3. Nobody has characterized the trajectory-position decay of behavioral signals
4. Nobody has compared introspective (behavioral exhaust) vs extrospective (cross-model) signals for agent actions
5. The structural faithfulness check (perturbation-based) applied to behavioral features is methodologically novel

## References (Full Citations)

- Chen et al. 2025, "Reasoning Models Don't Always Say What They Think," arXiv:2505.05410
- Lanham et al. 2023, "Measuring Faithfulness in Chain-of-Thought Reasoning," arXiv:2307.13702
- Greenblatt et al. 2024, "Alignment Faking in Large Language Models," arXiv:2412.14093
- Jones et al. 2025, "Forecasting Rare Language Model Behaviors," arXiv:2502.16797
- Yao et al. 2024, "tau-bench," arXiv:2406.12045
- Benton et al. 2024, "Sabotage Evaluations for Frontier Models," arXiv:2410.21514
- Hubinger et al. 2024, "Sleeper Agents," arXiv:2401.05566
- Sharma et al. 2023, "Towards Understanding Sycophancy," arXiv:2310.13548
- Khan et al. 2024, "Debating with More Persuasive LLMs," arXiv:2402.06782 (ICML 2024 Best Paper)
- Rabanser et al. 2026, "Towards a Science of AI Agent Reliability," arXiv:2602.16666
- Anthropic, "A Statistical Approach to Model Evaluations," anthropic.com/research
- Anthropic, "Building Effective Agents," anthropic.com/research
- Anthropic, "The Think Tool," anthropic.com/engineering
- Anthropic, "Demystifying Evals for AI Agents," anthropic.com/engineering
- Anthropic, "Effective Harnesses for Long-Running Agents," anthropic.com/engineering
- Anthropic, "Advanced Tool Use," anthropic.com/engineering
- Anthropic, "Bloom: Automated Behavioral Evaluations," alignment.anthropic.com/2025
