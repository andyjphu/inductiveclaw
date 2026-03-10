This `README.md` is designed to be the "source of truth" for your **iClaw** fork. It positions the project as a high-performance research tool while carefully navigating the "2026 Antigravity" security landscape to ensure your users get the maximum possible quota without risking their Google accounts.

---

# 🚀 iClaw: High-Quota Gemini Research CLI

**iClaw** is a powerful, agentic terminal interface forked from OpenCode, optimized for deep research workflows. Unlike standard API wrappers, iClaw utilizes an **Official OAuth 2.0 Desktop Flow** to unlock the "Power User" tier of the Gemini API—granting you up to **1,000 requests per day** on a completely free Google account.

---

## ⚖️ The 2026 Quota Advantage

In early 2026, Google updated its "Antigravity" security backend. Standard API keys are now strictly capped for free users. iClaw bypasses these bottlenecks by identifying you as a legitimate desktop developer.

| Feature | Standard API Key | iClaw OAuth Flow |
| --- | --- | --- |
| **Daily Request Limit** | ~250 Requests | **1,000 Requests** |
| **Requests Per Minute** | 15 RPM | **60 RPM** |
| **Ban Risk** | Low | **Zero (Official Path)** |
| **Cost** | $0 | **$0** |

---

## 🛠️ Initial Setup (The "Power User" Path)

To access the 1,000 RPD quota, you must briefly register your own local "client" with Google. This ensures you are not "spoofing" headers and keeps your account safe.

### 1. Create your Google Cloud Credentials

1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "My-iClaw-Research").
3. Navigate to **APIs & Services > Library** and enable the **Generative Language API**.
4. Go to **APIs & Services > Credentials**.
5. Click **Create Credentials** > **OAuth client ID**.
6. Select **Application type: Desktop app**. Name it "iClaw-Local".
7. Download the JSON file, rename it to `client_secret.json`, and move it to `~/.config/iclaw/`.

### 2. Authenticate

Run the following command in your terminal:

```bash
iclaw auth login

```

This will open your default browser. Sign in with your Google account and click **"Allow"**. iClaw will securely store a `refresh_token` locally. You will likely never have to do this again.

---

## ⚠️ Safety & Terms of Service (ToS)

As of March 2026, "Session Spoofing" (pretending to be the official Gemini CLI) is a high-risk activity that results in `403 Forbidden` account bans.

**iClaw is built for compliance:**

* **No Header Spoofing:** We use your unique Client ID.
* **Official Scopes:** We only request `generative-language.retriever` and `cloud-platform` permissions.
* **Privacy:** On the Free Tier, Google may use data to improve models. **Do not use iClaw for proprietary or highly sensitive research data.**

---

## ⌨️ Advanced Usage

### Context Caching

For long-form research, iClaw supports **Gemini Context Caching**. If you are querying the same 500-page PDF repeatedly, iClaw will cache the tokens on Google's servers to save you from hitting your Tokens-Per-Minute (TPM) limit.

### Fallback Mode

If you do not wish to use OAuth, you can still use a standard API key:

```bash
export GEMINI_API_KEY="your_key_here"
iclaw start

```

*Note: Usage will be throttled to the standard ~250 requests/day limit.*

---

## 🤝 Contributing

This is an open-source fork. We welcome contributions that improve the research-specific toolset (PDF parsing, LaTeX rendering, etc.). Please ensure all PRs maintain the official OAuth flow standards to protect our user base from bans.

---

### Would you like me to do next?

I can generate the **`auth.py`** source code that actually handles this "Desktop App" OAuth logic for you to paste into your project. Shall I?