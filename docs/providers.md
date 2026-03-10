# Providers

## Overview

InductiveClaw uses a multi-provider abstraction. Currently only Anthropic (Claude) is fully functional. OpenAI and Gemini are future features — their config scaffolding exists but the Agent SDK only supports Claude models.

## Anthropic (Claude) — Implemented

Two auth modes:

### OAuth (Max/Pro subscription)
- Requires: `claude` CLI installed + `claude login` completed
- Mechanism: strips `ANTHROPIC_API_KEY` from env so CLI falls through to stored OAuth credentials
- Pros: flat-rate subscription billing
- Cons: requires Max/Pro subscription

### API Key
- Mechanism: sets `ANTHROPIC_API_KEY` in env
- Pros: simple, works anywhere
- Cons: pay-per-token

## OpenAI — Future Feature

Config scaffolding exists for:
- **Codex App Server** — spawns `codex app-server`, JSON-RPC over stdio
- **API Key** — direct `OPENAI_API_KEY`

Not functional because the Agent SDK only calls the `claude` CLI. Implementing OpenAI requires a separate API client with its own tool-use loop.

## Gemini — Future Feature

Config scaffolding exists for:
- **Google OAuth** — Desktop app flow with `client_secret.json`
- **API Key** — direct `GEMINI_API_KEY`

Same limitation as OpenAI — requires a separate API client.

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

Currently only useful if you have multiple Anthropic API keys configured (edge case). Becomes meaningful when OpenAI/Gemini are implemented.

## Setup

`iclaw --setup` or `/config` in interactive mode runs the guided setup flow. Each provider shows its auth options with pros and cons.
