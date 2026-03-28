# Seed Reading List (Validated / Hygiene-Pass)

**Goal:** Small, high-signal seed set optimized for UGA / readiness-gated tool use. This list is **citation-hygiene corrected** and flags what is verified vs still pending.

Legend:
- **P0** = read first (project-design critical)
- **Verified** = landing page / library entry checked
- **ArXiv-first** = treat arXiv year as canonical unless we later add venue year as secondary

---

## P0 (Read first)

| Title | Canonical year (this corpus) | Venue (canonical) | Type | Bucket | Verified? | Notes |
|---|---:|---|---|---|---|---|
| On Calibration of Modern Neural Networks (Guo et al.) | 2017 | ICML (PMLR v70) | empirical/methods | B0 | ✅ | PMLR page verified. |
| Selective Classification for Deep Neural Networks (Geifman & El-Yaniv) | 2017 | NeurIPS | empirical | B0 | ⚠️ partial | Need to capture canonical proceedings link; PDF present. |
| Underspecification Presents Challenges for Credibility in Modern ML (D’Amour et al.) | 2020 | arXiv | critique/methods | B7 | ✅ | arXiv:2011.03395 |
| Holistic Evaluation of Language Models (Liang et al.) | 2022 | arXiv | benchmark/methods | B2 | ✅ | arXiv:2211.09110 |
| ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al.) | 2022 | arXiv-first | methods | B6 | ✅ | arXiv:2210.03629 (venue TBD) |
| SWE-bench: Can Language Models Resolve Real-World GitHub Issues? (Jimenez et al.) | 2023 | arXiv-first | benchmark | B2 | ✅ | arXiv:2310.06770 (seed list previously mislabeled 2024) |
| OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks… (Xie et al.) | 2024 | arXiv-first | benchmark | B2 | ✅ | arXiv:2404.07972 |
| Language Models (Mostly) Know What They Know (Kadavath et al.) | 2022 | arXiv | empirical | B1 | ✅ | arXiv:2207.05221 (seed list previously mislabeled 2021) |
| Shortcut Learning in Deep Neural Networks (Geirhos et al.) | 2020 | Nature MI (plus arXiv) | critique/survey | B7 | ⚠️ partial | PDF downloaded; capture canonical link next. |
| Classifier Technology and the Illusion of Progress (Hand) | 2006 | Statistical Science | critique | B7 | ✅ | Previously verified via Scholar/Project Euclid snippet. |

---

## P0 gaps (must add next; not yet downloaded)

These are explicitly required by the UGA program and are currently missing from the downloaded corpus.

| Target | Why it matters | Status |
|---|---|---|
| Platt (1999): Probabilistic outputs for SVMs / calibration | canonical post-hoc calibration reference | **Not yet acquired** |
| Chow (1970): reject option / error–reject tradeoff | canonical abstention formalization | **Not yet pinned down** (citation form unresolved) |
| SelectiveNet (2019) | modern learned reject option | **Not yet acquired** |
| Sadinle et al. (2019) (reject option / set-valued prediction) | alternative abstention formalism | **Not yet acquired** |
| Angelopoulos & Bates (2021) conformal intro | conformal methods as abstention control | **Not yet acquired** |

---

## P1/P2 (Downloaded but metadata verification pending)

| File | Bucket | Next step |
|---|---|---|
| 2022-Yao-WebShop.pdf | B2 | verify via arXiv landing page + correct title/year |
| 2023-Deng-Mind2Web.pdf | B2 | verify via arXiv landing page |
| 2023-Wang-LLMAgentsSurvey.pdf | B2 | verify via arXiv landing page |
| 2023-Wang-Voyager.pdf | B4 | verify via arXiv landing page |
| 2021-Bethard-DynaBench.pdf | B7 | verify via arXiv landing page |
| 2021-Ribeiro-CheckList.pdf | B7 | verify via arXiv landing page |
| 2021-Lin-TruthfulQA.pdf | B7 | already verified via arXiv; keep |

