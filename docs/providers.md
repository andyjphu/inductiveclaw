# Providers

## Overview

InductiveClaw supports three AI providers: Anthropic (Claude), OpenAI, and Google Gemini. Each has its own backend implementation with full tool-calling support. The `backends/` package abstracts away provider differences behind a unified protocol.

## Architecture

```
providers/          → Auth, config, API keys (who you are)
backends/           → Agent runtime (how the model runs)
  claude.py         → Claude Agent SDK (full agent runtime, OS sandbox, MCP)
  openai.py         → OpenAI chat completions + function calling
  gemini.py         → Google Gemini + function calling
  tool_executor.py  → Generic tool dispatch for non-Claude backends
  costs.py          → Token-based cost estimation
  base.py           → Unified message types and backend ABCs
```

## Anthropic (Claude)

Two auth modes:

### OAuth (Max/Pro subscription)
- Requires: `claude` CLI installed + `claude login` completed
- Mechanism: strips `ANTHROPIC_API_KEY` from env so CLI falls through to stored OAuth credentials
- Pros: flat-rate subscription billing, full Agent SDK features (OS sandbox, MCP, sub-agents)
- Cons: requires Max/Pro subscription

### API Key
- Mechanism: sets `ANTHROPIC_API_KEY` in env
- Pros: simple, works anywhere
- Cons: pay-per-token

### Claude-specific features
- OS-level sandbox (Seatbelt/bubblewrap) — kernel-level filesystem restrictions
- MCP tool server — custom tools registered natively
- Sub-agent support via Claude Agent SDK

## OpenAI

Install: `pip install iclaw[openai]`

Two auth modes:

### Codex App Server (ChatGPT subscription)
- Uses `codex` CLI (npm install -g @openai/codex)
- Browser-based auth
- Best for: interactive use with ChatGPT subscription

### API Key
- Set `OPENAI_API_KEY` or paste during setup
- Default model: `o3`
- Best for: automation, CI

### How it works
Uses OpenAI chat completions with function calling. The `ToolExecutor` handles tool dispatch with sandbox enforcement. Tools: bash, read/write files, glob, grep, plus all 6 iclaw custom tools.

## Gemini (Google)

Install: `pip install iclaw[gemini]`

Two auth modes:

### Google OAuth (Desktop App)
- Requires Google Cloud project + OAuth client credentials
- Higher rate limits (1000 req/day, 60 RPM on free tier)
- Best for: heavy free-tier usage

### API Key
- Get from https://aistudio.google.com/apikey
- Default model: `gemini-2.5-pro`
- Best for: quick setup, light usage

### How it works
Uses google-genai SDK with function calling. Same `ToolExecutor` as OpenAI for tool dispatch.

## Provider Registry

`ProviderRegistry` in `providers/__init__.py`:
- Manages all providers
- Persists config to `~/.config/iclaw/providers.json`
- Handles rate-limit cycling between configured providers
- Auto-detects Anthropic OAuth/API key on first run

## Rate-Limit Cycling

When enabled (requires 2+ providers configured):
- On rate limit error, record a hit in `RateLimitTracker`
- 2 hits within 5 minutes → provider marked as exhausted for the day
- Cycle to next configured provider in order
- If all exhausted → stop

Works across all providers — e.g., cycle from Claude to OpenAI to Gemini.

## Cost Tracking

- **Claude**: SDK provides `total_cost_usd` directly
- **OpenAI/Gemini**: Estimated from token counts using published pricing (`backends/costs.py`)
- Cost displays in both interactive (`/cost`) and autonomous mode summaries

## Setup

`iclaw --setup` or `/config` in interactive mode runs the guided setup flow. Each provider shows its auth options with pros and cons.
