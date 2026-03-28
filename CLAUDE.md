# UGA Harness

A standalone, open-source agent harness that implements uncertainty-gated autonomy for coding agents.

## What This Is
A novel agent harness that wraps ACP-compatible coding agents (Claude Code, Codex) and implements:
- Tool call interception with configurable gate policies
- Calibrated confidence elicitation (zero-shot + few-shot P(True))
- Critic-disagreement mechanism (multi-agent verification)
- Structured decision logging and trace collection
- Benchmark suite for evaluating gated vs ungated agent reliability

## Target
Application artifact for Anthropic Research Engineer, Agents role.

## Context
Prior research design work is in context/ directory.
Literature corpus is at ~/.openclaw/workspace/ops/lit/

## Architecture Principles
- Standalone (no dependency on OpenClaw or any specific orchestrator)
- ACP-native (works with any ACP-compatible agent)
- Observable (every decision point is logged)
- Configurable (gate policies are pluggable)
- Benchmarkable (ships with evaluation suite)
