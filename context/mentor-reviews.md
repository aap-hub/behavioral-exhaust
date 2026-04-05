# Mentor Reviews — Pre-Build Sanity Check

Two independent Opus 4.6 reviews from different perspectives. Read both before building.

## Mentor 1: Anthropic RE Hiring Committee Perspective

### Verdict: Interview YES. But stop designing, start building.

**Signal vs noise:** ~65% real substance, ~20% scaffolding, ~15% to cut. The operational definitions glossary (§0) costs 4 pages before the research question — move to appendix. Mechanism specs (§8) belong in code comments, not the research design. Section 14 ("What I noticed about how you think") — cut from submission.

**What impresses:**
- Research question pivot is exactly right (from "does gating help?" to "when is the signal trustworthy?")
- Literature engagement is genuine, not decorative (17+ Anthropic pubs actually used)
- Tier 0/Tier 1 decomposition shows experimental hygiene most candidates skip
- Calibration-first design is epistemically clean
- Not afraid of negative results (go/no-go includes characterized negative)
- Handled devastating Codex reviews with controlled imports, not defense or collapse

**What worries:**
- NO CODE EXISTS YET. Design doc is not a built project. JD asks for "a project built on LLMs."
- Scope may be too large for 12 days. Has seen this pattern before: ambitious design, executed Phase 0, ran out of time.
- Over-indexing on statistical machinery at n=50. A scatter plot will tell more than a Vuong test.
- Cross-model comparison depends on brittle Codex parsing.

**Scope recommendation: Phase 0 only for the submission.** Run tasks, collect traces, extract features, compute the interaction matrix. Skip cross-model comparison. Skip Phase 1 (describe as planned). Deliver: working code, populated SQLite, real interaction matrix, 3-4 page memo.

**The slam dunk:** Produce the Phase 0 interaction matrix WITH REAL DATA. Real ρ values from actual Claude Code traces. Any outcome (positive, negative, mixed) backed by real data beats a perfect plan.

**Ranking:** As design: Top 5-10%. As complete artifact: currently Top 25%, potentially Top 5-10% with real data.

---

## Mentor 2: Senior Agent Systems Builder Perspective

### Verdict: Research design A-tier. Engineering plan B-minus.

**Will it work?** Phase 0 will work (post-hoc analysis, stable interfaces). Phase 1 hook integration is the highest risk point. Four specific problems:
1. Hook stdin contract underspecified
2. Codex inside a hook = 3 process boundaries + network, will blow overhead budget
3. No conversation history available to hook for critic prompt
4. Python cold start compounds with Codex latency

**Overengineered:**
- SQLite schema over-normalized (5 tables for ~180 rows). Flatten labels into tool_calls.
- Vuong test at n=50 with 10 clusters — no power. Use scatter plots.
- Faithfulness check — full day for secondary result that doesn't affect go/no-go. Skip it.
- Anonymization pipeline — find-and-replace is sufficient for an application artifact.
- Power analysis formalism — just run a smoke test.

**Underengineered:**
- Stream-json parser is the MOST IMPORTANT code and gets ONE LINE in §8.1
- No workspace reset between Phase 1 replicates
- No labeling interface (the tool the human actually interacts with)
- No error recovery for crashed runs
- Codex CLI not verified (access, latency, parsability)
- Task runner doesn't address git workspace isolation

**Build order fix — the actual Day 0:**
1. Hours 1-2: Prove the hook works (write trivial hook, verify stdin, test exit code 2)
2. Hours 2-4: Prove stream-json parsing works (run real task, write parser)
3. Hours 4-6: Prove Codex exec works (measure latency, parse response)
4. Hours 6-8: One full end-to-end loop (task → trace → features → label → one ρ)

**Task sourcing (the unaddressed bottleneck):**
Recommended: 6 from SWE-bench Lite + 4 synthetic. Each must generate 5+ state-modifying calls. Test on Day 0 smoke test.

**The demo (2-minute video):**
- 0:00-0:15: Live hook intercepting tool calls, scoring in real-time
- 0:15-0:45: Gate blocks a bad call, agent adapts
- 0:45-1:15: Interaction matrix heatmap
- 1:15-1:45: Risk-coverage curve
- 1:45-2:00: "Harness, data, analysis are open source." Show repo.
Do NOT show code, literature, or schema. Show running systems and results.

**The single most important thing:** Get one task end-to-end on Day 0. If that loop works by end of Day 0, the project ships.

---

## Where Both Mentors Agree

1. **Stop designing. Start building.** The design is strong enough. Real data > perfect plan.
2. **Phase 0 only for the submission.** Don't try to ship both phases in 12 days.
3. **The interaction matrix with real numbers IS the artifact.** Any outcome backed by data beats the spec.
4. **Cut the statistical machinery.** Vuong test, faithfulness check, power analysis formalism — all cut. Use scatter plots and simple correlations at this sample size.
5. **Day 0 = end-to-end smoke test.** Hook verification, stream-json parser, one task through the full loop.
6. **Task sourcing is the bottleneck nobody addressed.** SWE-bench Lite subset is the fastest path.
