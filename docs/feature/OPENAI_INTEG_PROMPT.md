Paste this as `codex-integration-feature-implementation-instructions.md`.

The OpenAI-specific wording below is anchored to the current official Codex docs: Codex app-server is documented for “deep integration inside your own product,” supports authentication flows including ChatGPT and API key sign-in, and uses JSON-RPC with `stdio` as the default transport. OpenAI’s terms also make clear that supported integration is not a guarantee against suspension or termination if policies or terms are violated. ([OpenAI Developers][1])

The OpenCode comparison section is based on OpenCode’s public docs and repo materials showing a client/server architecture, API-key-oriented auth docs, local auth storage, and ecosystem plugins for Codex-auth style subscription use. ([GitHub][2])

````md
# Codex integration feature implementation instructions

## Purpose

This document gives implementation instructions for adding **officially supported OpenAI Codex integration** to the InductiveClaw CLI (`iclaw`) while preserving the current Claude-oriented default setup flow.

It includes:

- the legal/policy framing
- the supported process architecture
- the implementation prompt for an AI coding agent
- human-facing docs
- AI/dev-facing docs
- README wording
- verification checklist
- a brief OpenCode comparison

---

## Status and scope

This feature is intended to add **OpenAI Codex support using OpenAI’s documented Codex auth/app-server flow**.

It does **not** attempt to:

- scrape browser cookies
- replay undocumented ChatGPT web tokens
- reverse engineer hidden auth flows
- claim immunity from enforcement
- block on Gemini implementation details

Claude remains the default onboarding path. OpenAI Codex is added as an **explicit setup option** via `iclaw --setup`.

---

## Executive summary

### What we are doing

We are adding OpenAI Codex support to InductiveClaw in the **supported** way:

- `iclaw` remains the user-facing CLI
- `codex app-server` is spawned as a helper/backend process
- `iclaw` talks to `codex app-server` over stdio JSON-RPC
- for ChatGPT-backed Codex auth, `iclaw` asks app-server to start login
- app-server returns an `authUrl`
- the browser opens the official login flow
- app-server handles the local callback and token lifecycle

### What we are not doing

We are **not** implementing a “token hack,” “loophole,” or cookie-based shortcut.

### Why this is the right approach

This follows the documented Codex integration path and keeps auth ownership where it belongs:

- OpenAI/Codex handles Codex-specific auth
- `iclaw` handles user experience, orchestration, and provider selection

---

## Legal and policy standing

### Accurate claim

The accurate claim is:

> InductiveClaw supports OpenAI Codex through OpenAI’s documented Codex auth/app-server flow, which is a supported integration path for a custom product.

### Also important

Do **not** say:

- “this cannot get you banned”
- “this is unbannable”
- “this is a loophole”
- “this bypasses limits”
- “this uses a hidden OAuth trick”

### Correct cautionary wording

Use this instead:

> Supported does not mean guaranteed immunity from account enforcement. OpenAI Terms and Usage Policies still apply.

### Why this wording matters

Even when an auth flow is documented and supported, account use remains subject to platform rules, policies, and enforcement. That means supported integration is **not** the same thing as a blanket legal or enforcement guarantee.

### Not legal advice

This documentation is a technical implementation guide and product-policy framing document. It is **not** legal advice.

---

## Product requirements

### Default behavior

The current Claude/Anthropic default path stays the default.

That means:

- existing users should not be silently moved to OpenAI
- the current Claude-oriented onboarding should remain intact
- OpenAI Codex should be added as a deliberate provider setup choice

### New setup behavior

Add:

- `iclaw --setup`

This is the guided multi-provider setup flow.

Inside `iclaw --setup`, show options for:

- Claude / Anthropic
- OpenAI Codex
- Gemini usage pooling setup or placeholder

### OpenAI setup choices

When the user chooses OpenAI, offer:

1. **Sign in with ChatGPT**  
   Recommended for interactive Codex use.

2. **Use OpenAI API key**  
   Recommended for automation, CI, or explicit usage-based billing.

### Provider status UX

Add provider status states such as:

- Claude: connected / not connected
- OpenAI: connected via ChatGPT / connected via API key / not connected
- Gemini: configured elsewhere / not configured

### Suggested commands

Examples:

- `iclaw --setup`
- `iclaw provider status`
- `iclaw provider use openai`
- `iclaw openai login`
- `iclaw openai logout`

---

## Supported process architecture

### Core model

The intended architecture is:

- **InductiveClaw CLI** = orchestrator / UX layer
- **Codex app-server** = OpenAI-specific helper/backend
- **Browser** = only for the official ChatGPT login hop
- **OpenAI** = actual account auth + Codex backend

### Process relationship

In practice, `iclaw` should usually:

1. start or connect to `codex app-server`
2. communicate with it over stdio JSON-RPC
3. delegate OpenAI auth lifecycle to app-server

That means InductiveClaw does **not** implement ChatGPT OAuth itself.

### Why this matters

It keeps the integration aligned with the documented Codex contract instead of inventing a new unsupported auth path.

---

## OpenAI auth modes to implement

### Implement now

Implement these OpenAI modes:

- `chatgpt`
- `apikey`

### Do not implement now

Do **not** implement `chatgptAuthTokens` unless you genuinely own a documented host-side token lifecycle and can safely refresh tokens on request.

For InductiveClaw, the normal recommendation is:

- use `chatgpt` for managed ChatGPT-backed login
- use `apikey` for API-billed usage
- do not use `chatgptAuthTokens` by default

---

## OpenAI auth flow details

### Initial account check

On OpenAI provider initialization:

1. start `codex app-server`
2. call `account/read`
3. inspect whether a valid account session already exists

### ChatGPT-managed login flow

If the user chooses ChatGPT-backed sign-in:

1. call `account/login/start` with `{ "type": "chatgpt" }`
2. receive `authUrl`
3. open `authUrl` in the user’s browser
4. wait for `account/login/completed`
5. update local UI/state on `account/updated`

### API key login flow

If the user chooses API key auth:

1. call `account/login/start` with `{ "type": "apiKey", "apiKey": "..." }`
2. update local UI/state when login succeeds
3. store secrets only through approved secure local secret storage

### Logout flow

Support:

- `account/logout`

### Optional status/rate-limit flow

If available, read:

- `account/rateLimits/read`

and display a small, clear summary.

---

## Security requirements

### Never do these things

Do **not**:

- read browser cookies
- ask the user to paste ChatGPT session cookies
- use undocumented ChatGPT web endpoints
- replay raw browser tokens
- log access tokens, ID tokens, cookies, or API keys
- send secrets into telemetry or crash logs
- print secrets in debug output

### Secret storage

Preferred:

- OS credential store

If local files are used:

- document location clearly
- lock down permissions
- avoid plaintext exposure in logs or screenshots

### Required tests

Add tests to verify:

- tokens are never logged
- auth state transitions are correct
- provider switching does not leak secrets
- logout clears usable local auth state as expected

---

## Non-goals and constraints

### Hard constraints

- preserve Claude as the default onboarding path
- implement OpenAI as an explicit setup path
- do not require Gemini details to ship OpenAI support
- do not overclaim legal safety
- do not market this as a workaround or exploit

### Gemini note

Gemini setup may appear in `iclaw --setup`, but Gemini implementation details are handled elsewhere.

For this feature:

- add Gemini setup hooks or placeholders only
- do not block the OpenAI work on Gemini
- do not make legal claims about Gemini here

---

## Recommended internal state model

A suggested provider state model for OpenAI:

- `not_configured`
- `configuring`
- `login_pending`
- `connected_chatgpt`
- `connected_apikey`
- `login_failed`
- `logged_out`

You may also track:

- `plan_type`
- `rate_limit_summary`
- `last_auth_error`

---

## Implementation prompt for your AI coding agent

```text
You are modifying the InductiveClaw CLI ("iclaw") to add OFFICIAL OpenAI Codex support using OpenAI’s documented Codex app-server authentication flow.

Primary goal
- Add OpenAI Codex as a first-class provider in a supported way.
- Keep the current Claude Code OAuth/default flow as the default onboarding path for iclaw.
- Add `iclaw --setup` as the explicit multi-provider setup entrypoint where users can also configure:
  - OpenAI Codex via official Codex app-server auth
  - Gemini usage-pooling integration hooks/config (implemented separately; do not block this work on Gemini details)

Hard constraints
- Do NOT scrape browser cookies.
- Do NOT ask users to paste ChatGPT session cookies.
- Do NOT reverse engineer undocumented ChatGPT web auth endpoints.
- Do NOT claim “cannot get you banned”, “unbannable”, “loophole”, or “bypass”.
- Do NOT implement raw token replay from a browser session.
- Do NOT make Gemini implementation details a dependency for the OpenAI work.
- Prefer Codex app-server managed `chatgpt` mode.
- Allow API-key fallback for OpenAI.

Supported facts to align with
- Codex app-server is documented for “deep integration inside your own product”.
- Codex app-server supports `apikey`, `chatgpt`, and `chatgptAuthTokens`.
- In `chatgpt` mode, app-server owns the browser login callback and token refresh.
- Codex supports ChatGPT sign-in for subscription access and API-key sign-in for usage-based access.
- Codex CLI uses ChatGPT sign-in as the default path when no valid session is available.
- OpenAI Terms/Policies still apply; supported auth path does not guarantee immunity from account action.

Target product behavior
1. Default behavior
   - Preserve the existing Claude Code OAuth/default auth behavior as the default experience in iclaw.
   - Do not unexpectedly replace the default provider for existing users.

2. Setup flow
   - Add `iclaw --setup` as the guided provider setup flow.
   - In setup, show:
     - Claude / Anthropic setup
     - OpenAI Codex setup
     - Gemini pooling setup placeholder / external hook
   - OpenAI setup should offer:
     - “Sign in with ChatGPT (recommended for interactive Codex use)”
     - “Use OpenAI API key”

3. OpenAI architecture
   - Implement OpenAI support by spawning `codex app-server` as a child process.
   - Use stdio JSON-RPC as the transport.
   - Add an internal OpenAI auth/service layer that:
     - starts app-server
     - calls `account/read`
     - if needed calls `account/login/start`
     - opens `authUrl` in browser for `chatgpt`
     - listens for `account/login/completed`
     - listens for `account/updated`
     - supports `account/logout`
     - optionally reads `account/rateLimits/read`
   - Do not implement `chatgptAuthTokens` unless there is a clearly documented host-owned token lifecycle. For now, treat that mode as unsupported in iclaw.

4. UX requirements
   - Default iclaw launch path remains Claude-oriented as it is today.
   - `iclaw --setup` becomes the place to add or switch providers.
   - Add provider status output such as:
     - Claude: connected / not connected
     - OpenAI: connected via ChatGPT / connected via API key / not connected
     - Gemini: configured elsewhere / not configured
   - Add commands or menu actions for:
     - login
     - logout
     - status
     - provider switch
   - If OpenAI `account/read` returns `planType`, display it.
   - If `account/rateLimits/read` succeeds, display a concise rate-limit summary.

5. Security requirements
   - Never log access tokens, id tokens, session cookies, or API keys.
   - Redact credentials from debug logs, telemetry, and crash output.
   - Use OS credential store when possible.
   - If local files are used, document them and keep permissions strict.
   - Add tests asserting tokens are never printed.

6. Documentation requirements
   Create or update:
   - `docs/human/codex-openai-auth.md`
   - `docs/ai/codex-openai-auth.md`
   - README/provider setup section
   - migration notes / changelog entry

7. Required wording constraints in docs
   Allowed wording:
   - “InductiveClaw supports OpenAI Codex through OpenAI’s documented Codex auth/app-server flow.”
   - “This is a supported integration path.”
   - “Supported does not mean guaranteed immunity from account enforcement; OpenAI Terms and Usage Policies still apply.”
   Not allowed:
   - “This cannot get you banned.”
   - “This is a loophole.”
   - “This bypasses limits.”
   - “This uses hidden or scraped OAuth.”

8. Implementation details to prefer
   - Abstraction:
     - provider_id = `anthropic` | `openai` | `gemini`
     - auth_mode for OpenAI = `chatgpt` | `apikey`
   - Process model:
     - iclaw is the orchestrator/UI
     - codex app-server is the OpenAI-specific backend helper
   - Lifecycle:
     - start app-server lazily when OpenAI is selected or configured
     - cache status
     - reconnect on restart
     - allow logout to clear OpenAI state cleanly

9. Gemini note
   - Add Gemini setup entrypoints/config placeholders in `iclaw --setup`.
   - Do not invent legal claims for Gemini.
   - Do not block the OpenAI implementation on Gemini work.
   - Make Gemini a pluggable provider integration point to be implemented elsewhere.

10. Deliverables
   - architecture plan
   - exact files to change
   - implementation
   - docs for humans
   - docs for AI/devs
   - README updates
   - tests
   - verification checklist

Output format
- First: architecture summary
- Second: file-by-file change plan
- Third: full diffs or full files
- Fourth: docs text
- Fifth: verification checklist
- Sixth: explicit note of any assumptions or undocumented areas not implemented
````

---

## Human-facing documentation

Save as:

* `docs/human/codex-openai-auth.md`

```md
# OpenAI Codex authentication in InductiveClaw

InductiveClaw supports OpenAI Codex through OpenAI’s documented Codex authentication and app-server flow.

## What this means

When you use OpenAI Codex in InductiveClaw, the recommended path is:

- InductiveClaw starts the local Codex app-server helper
- InductiveClaw asks Codex app-server to begin login
- your browser opens the official ChatGPT login page
- Codex app-server receives the local callback
- Codex app-server stores and refreshes the Codex session

InductiveClaw does not need to scrape browser cookies or use undocumented ChatGPT web endpoints.

## Supported OpenAI sign-in methods

InductiveClaw supports two OpenAI sign-in modes:

1. **Sign in with ChatGPT**
   - Uses your ChatGPT-backed Codex access when available
   - Best for interactive local use

2. **Sign in with an OpenAI API key**
   - Uses standard OpenAI API billing
   - Best for automation or explicit usage-based billing

## Default behavior

InductiveClaw keeps its existing default Claude-oriented onboarding behavior.

If you want to add OpenAI Codex, run:

`iclaw --setup`

That setup flow lets you configure additional providers, including OpenAI.

## What InductiveClaw does not do

For OpenAI Codex auth, InductiveClaw does **not**:

- read your browser cookies
- ask you to paste ChatGPT session cookies
- use undocumented ChatGPT auth endpoints
- replay raw browser tokens
- market the flow as a loophole or bypass

## Legal / policy standing

This is a supported integration path because it is built on OpenAI’s documented Codex auth and app-server interfaces.

However, “supported” does **not** mean “immune from enforcement.” Your use of OpenAI services is still subject to OpenAI’s Terms and Usage Policies. Misuse, policy violations, or risky behavior can still lead to warnings, restrictions, suspension, or termination by OpenAI.

This document is a technical explanation, not legal advice.

## Recommendation

- Use **ChatGPT sign-in** for personal interactive Codex use.
- Use **API key** auth for automation and CI.
- Use `iclaw --setup` to add or switch providers deliberately.
```

---

## AI/dev-facing documentation

Save as:

* `docs/ai/codex-openai-auth.md`

```md
# AI/dev notes: OpenAI Codex auth in InductiveClaw

## Objective

Implement OpenAI Codex support only through documented OpenAI Codex interfaces.

## Approved architecture

- `iclaw` is the orchestrator / UX layer
- `codex app-server` is the OpenAI-specific local backend helper
- transport is stdio JSON-RPC
- browser is used only for the official ChatGPT login hop

## Approved OpenAI auth modes

Use only:

- `chatgpt`
- `apikey`

Do not implement `chatgptAuthTokens` unless the host application genuinely owns a documented ChatGPT token lifecycle and can refresh tokens on request.

## Required flow

### Check auth state
Call:
- `account/read`

### API key login
Call:
- `account/login/start` with `{ "type": "apiKey", "apiKey": "..." }`

Then observe:
- `account/login/completed`
- `account/updated`

### ChatGPT managed login
Call:
- `account/login/start` with `{ "type": "chatgpt" }`

Then:
- open returned `authUrl` in the browser
- wait for `account/login/completed`
- update local state on `account/updated`

### Logout
Call:
- `account/logout`

### Optional status
Call:
- `account/rateLimits/read`

## Security rules

Never implement any of the following:
- cookie scraping
- undocumented ChatGPT endpoint usage
- browser-token replay
- asking users for session cookies
- printing tokens to logs
- persisting secrets in unsafe debug traces

## Messaging rules

Allowed:
- “InductiveClaw uses OpenAI’s documented Codex app-server/auth flow.”
- “OpenAI Codex is integrated through a supported path.”
- “OpenAI Terms and Usage Policies still apply.”

Forbidden:
- “This cannot get you banned.”
- “This is an OAuth trick.”
- “This bypasses limits.”
- “This is a loophole.”
- “This uses hidden ChatGPT credentials.”

## Product behavior constraints

- Preserve existing Claude-oriented default onboarding.
- Put OpenAI configuration behind `iclaw --setup`.
- OpenAI is an additional provider, not a silent replacement of the current default.
- Gemini setup may appear in the same setup UX, but Gemini implementation/legal assertions are out of scope here.

## State model

Recommended OpenAI provider state:
- `not_configured`
- `configuring`
- `connected_chatgpt`
- `connected_apikey`
- `login_pending`
- `login_failed`
- `logged_out`

## Suggested commands

- `iclaw --setup`
- `iclaw provider status`
- `iclaw provider use openai`
- `iclaw openai login`
- `iclaw openai logout`

## Compliance note

The basis for this integration is that OpenAI documents Codex app-server for deep integration into a custom product and documents supported account/auth flows for Codex clients. This does not override OpenAI’s Terms, Usage Policies, or administrative controls.
```

---

## README wording

Use this for a concise README section:

```md
### OpenAI Codex

InductiveClaw supports OpenAI Codex through OpenAI’s documented Codex auth/app-server flow.

The default onboarding path remains Claude-oriented. To add OpenAI Codex, run:

`iclaw --setup`

OpenAI Codex can be configured with:
- ChatGPT sign-in
- OpenAI API key

This integration uses documented interfaces only. OpenAI Terms and Usage Policies still apply.
```

---

## Suggested implementation structure

This is one reasonable module layout. Adapt to your codebase as needed.

```text
src/
  commands/
    setup.ts
    provider_status.ts
    openai_login.ts
    openai_logout.ts

  providers/
    registry.ts
    anthropic/
      index.ts
    openai/
      index.ts
      codex_app_server.ts
      codex_auth_service.ts
      codex_types.ts
      codex_rate_limits.ts
    gemini/
      index.ts
      setup_placeholder.ts

  security/
    secrets.ts
    redaction.ts

  ui/
    provider_selector.ts
    status_output.ts

docs/
  human/
    codex-openai-auth.md
  ai/
    codex-openai-auth.md

README.md
CHANGELOG.md
```

---

## Suggested implementation steps

1. add provider abstraction for `anthropic`, `openai`, and `gemini`
2. add `iclaw --setup`
3. preserve Claude as default setup path
4. add OpenAI provider selection in setup
5. create `codex_app_server` process wrapper
6. implement JSON-RPC request/response and notification handling
7. implement `account/read`
8. implement ChatGPT login flow
9. implement API key login flow
10. implement logout
11. implement provider status output
12. implement secure credential storage and redaction
13. add tests
14. add docs
15. add migration notes

---

## Verification checklist

### Auth and setup

* [ ] Existing Claude default onboarding still works unchanged
* [ ] `iclaw --setup` shows Claude, OpenAI, and Gemini setup entries
* [ ] OpenAI setup offers ChatGPT and API key sign-in
* [ ] OpenAI ChatGPT sign-in opens browser successfully
* [ ] OpenAI login completes through app-server callback
* [ ] `account/read` reflects authenticated state after login
* [ ] API key flow succeeds when a valid key is supplied
* [ ] logout clears usable OpenAI auth state
* [ ] provider switching works cleanly

### Security

* [ ] no tokens are printed to logs
* [ ] no cookies are requested from the user
* [ ] crash output redacts secrets
* [ ] debug traces redact secrets
* [ ] secret storage location and behavior are documented

### UX

* [ ] status clearly shows provider connection state
* [ ] OpenAI status distinguishes ChatGPT-backed vs API-key-backed auth
* [ ] setup flow does not silently replace existing default provider behavior
* [ ] failure states are understandable

### Documentation

* [ ] human docs use “supported integration path”
* [ ] human docs do not say “cannot get you banned”
* [ ] AI docs prohibit cookie scraping and undocumented auth flows
* [ ] README reflects the actual implementation
* [ ] changelog or migration notes mention the new setup behavior

---

## Assumptions and conservative limits

This document intentionally makes the following conservative choices:

* OpenAI support is implemented through `chatgpt` and `apikey`
* `chatgptAuthTokens` is explicitly out of scope unless the host truly owns a documented token lifecycle
* Gemini support is placeholder-only in this implementation document
* legal claims are deliberately narrow and non-absolute

If any part of the OpenAI surface appears undocumented in practice, do **not** implement it as official support.

---

## Short legal-safe wording snippets

These are safe snippets you can reuse.

### Good

* “InductiveClaw supports OpenAI Codex through OpenAI’s documented Codex auth/app-server flow.”
* “This is a supported integration path.”
* “Supported does not mean guaranteed immunity from account enforcement; OpenAI Terms and Usage Policies still apply.”

### Bad

* “This cannot get you banned.”
* “This is a loophole.”
* “This bypasses normal limits.”
* “This uses scraped OAuth.”
* “This is a hidden token trick.”

---

## Is this what OpenCode does?

### Short answer

Not exactly.

### More precise answer

OpenCode is clearly in a similar architectural neighborhood because it already has a client/server architecture and supports many providers.

However, its public documentation has historically emphasized provider auth through stored credentials and API-key-oriented flows, and its ecosystem also includes community plugins for subscription-backed Codex/Gemini auth-style behavior.

So the cleanest way to describe the relationship is:

* OpenCode is **similar in spirit**
* OpenCode is **not the exact canonical model** for the official Codex app-server pattern described here
* InductiveClaw should make the OpenAI path explicit and documented as:

  * `iclaw` as the orchestrator
  * `codex app-server` as the OpenAI-specific helper
  * official ChatGPT-managed login for ChatGPT-backed Codex access

### Recommendation

For InductiveClaw, prefer the clearer and more explicit implementation:

* default existing Claude flow stays default
* `iclaw --setup` is the multi-provider onboarding entrypoint
* OpenAI Codex is implemented through `codex app-server`
* docs say **supported**, not “risk-free”
* Gemini is handled separately

---

## Final recommendation

Ship this feature with the following principles:

1. preserve current default Claude behavior
2. add OpenAI through `iclaw --setup`
3. integrate OpenAI via `codex app-server`
4. support `chatgpt` and `apikey`
5. do not ship `chatgptAuthTokens` by default
6. never market the path as a loophole
7. keep docs explicit, conservative, and implementation-accurate

```

The most important current claims in that doc are supported by OpenAI’s official Codex auth/app-server docs and its terms: Codex clients support ChatGPT and API key sign-in; app-server is intended for deep product integration and uses JSON-RPC with `stdio`; and OpenAI reserves the right to suspend or terminate access for term/policy breaches or risk/harm. :contentReference[oaicite:2]{index=2}
::contentReference[oaicite:3]{index=3}
```

[1]: https://developers.openai.com/codex/app-server/?utm_source=chatgpt.com "Codex App Server"
[2]: https://github.com/anomalyco/opencode?utm_source=chatgpt.com "anomalyco/opencode: The open source coding agent."
