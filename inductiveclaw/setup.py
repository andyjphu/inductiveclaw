"""Guided provider setup flow — iclaw --setup or /config."""

from __future__ import annotations

from .providers import (
    AuthMode,
    ProviderConfig,
    ProviderID,
    ProviderRegistry,
)
from .providers.openai import CODEX_APP_SERVER_INFO, OPENAI_API_KEY_INFO
from .providers.gemini import GOOGLE_OAUTH_INFO, GEMINI_API_KEY_INFO

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm

    console = Console()
    _has_rich = True
except ImportError:
    console = None  # type: ignore[assignment]
    _has_rich = False


def _input(prompt: str) -> str:
    if _has_rich:
        return Prompt.ask(prompt)
    return input(f"{prompt}: ")


def _confirm(prompt: str, default: bool = False) -> bool:
    if _has_rich:
        return Confirm.ask(prompt, default=default)
    resp = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not resp:
        return default
    return resp in ("y", "yes")


def _print(text: str) -> None:
    if _has_rich:
        console.print(text)
    else:
        print(text)


def _panel(text: str, title: str = "") -> None:
    if _has_rich:
        console.print(Panel(text, title=title, border_style="cyan"))
    else:
        print(f"\n--- {title} ---")
        print(text)
        print()


def run_setup(registry: ProviderRegistry) -> None:
    """Run the guided multi-provider setup flow."""
    _print("\n[bold]InductiveClaw Provider Setup[/bold]\n" if _has_rich else "\nInductiveClaw Provider Setup\n")
    _print("Configure one or more AI providers. You can change these later with /config.\n")

    # Show current status
    _show_status(registry)

    # Configure providers
    _setup_anthropic(registry)
    _setup_openai(registry)
    _setup_gemini(registry)

    # Provider selection
    configured = registry.configured_providers()
    if not configured:
        _print("\n[bold red]No providers configured.[/bold red]" if _has_rich else "\nNo providers configured.")
        _print("Run iclaw --setup again to configure a provider.\n")
        return

    _select_active_provider(registry)
    _setup_cycling(registry)

    registry.save_config()
    _print("\n[bold green]Setup complete![/bold green]\n" if _has_rich else "\nSetup complete!\n")
    _show_status(registry)


def _show_status(registry: ProviderRegistry) -> None:
    if _has_rich:
        table = Table(title="Provider Status", show_header=True, border_style="dim")
        table.add_column("Provider", style="bold")
        table.add_column("Status")
        table.add_column("Active", justify="center")
        for pid, provider in registry.providers.items():
            active = "*" if pid == registry.active_id else ""
            table.add_row(provider.display_name, provider.status_line(), active)
        console.print(table)
        console.print()
    else:
        print("\nProvider Status:")
        for pid, provider in registry.providers.items():
            active = " [active]" if pid == registry.active_id else ""
            print(f"  {provider.display_name}: {provider.status_line()}{active}")
        print()


def _setup_anthropic(registry: ProviderRegistry) -> None:
    if not _confirm("Configure Claude (Anthropic)?", default=True):
        return

    _print("\n  [bold]Option 1:[/bold] OAuth (Max/Pro subscription)" if _has_rich else "\n  Option 1: OAuth (Max/Pro subscription)")
    _print("    Requires: claude CLI installed + `claude login` completed")
    _print("    Pros: Flat-rate subscription billing, no per-token cost")
    _print("    Cons: Must have Max/Pro subscription\n")

    _print("  [bold]Option 2:[/bold] API Key" if _has_rich else "  Option 2: API Key")
    _print("    Pros: Simple, works anywhere")
    _print("    Cons: Pay-per-token billing\n")

    choice = _input("Choose [1] OAuth or [2] API Key").strip()

    provider = registry.providers[ProviderID.ANTHROPIC]
    if choice == "2":
        key = _input("Enter your ANTHROPIC_API_KEY (or press enter for env var)")
        config = ProviderConfig(
            provider_id=ProviderID.ANTHROPIC,
            auth_mode=AuthMode.API_KEY,
            api_key=key if key.strip() else None,
            enabled=True,
        )
    else:
        _print("  Checking for Claude CLI...")
        from .providers.anthropic import _has_claude_cli, _has_oauth_credentials

        if not _has_claude_cli():
            _print("  [yellow]Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code[/yellow]" if _has_rich else "  Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code")
            _print("  Then run: claude login")
            return
        if not _has_oauth_credentials():
            _print("  [yellow]No OAuth credentials found. Run: claude login[/yellow]" if _has_rich else "  No OAuth credentials found. Run: claude login")
            return
        _print("  [green]OAuth credentials detected.[/green]" if _has_rich else "  OAuth credentials detected.")
        config = ProviderConfig(
            provider_id=ProviderID.ANTHROPIC,
            auth_mode=AuthMode.OAUTH,
            enabled=True,
        )

    provider.configure(config)


def _setup_openai(registry: ProviderRegistry) -> None:
    if not _confirm("\nConfigure OpenAI (Codex)?", default=False):
        return

    _panel(CODEX_APP_SERVER_INFO, title="Option 1")
    _panel(OPENAI_API_KEY_INFO, title="Option 2")

    choice = _input("Choose [1] Codex App Server or [2] API Key").strip()

    if choice == "1":
        import shutil

        if not shutil.which("codex"):
            _print("  [yellow]Codex CLI not found.[/yellow]" if _has_rich else "  Codex CLI not found.")
            _print("  Install: npm install -g @openai/codex")
            _print("  Then run: codex auth login")
            if not _confirm("  Continue anyway (you can install later)?"):
                return
        config = ProviderConfig(
            provider_id=ProviderID.OPENAI,
            auth_mode=AuthMode.CODEX_APP_SERVER,
            enabled=True,
        )
    else:
        key = _input("Enter your OPENAI_API_KEY (or press enter for env var)")
        config = ProviderConfig(
            provider_id=ProviderID.OPENAI,
            auth_mode=AuthMode.OPENAI_API_KEY,
            api_key=key if key.strip() else None,
            enabled=True,
        )

    registry.providers[ProviderID.OPENAI].configure(config)


def _setup_gemini(registry: ProviderRegistry) -> None:
    if not _confirm("\nConfigure Gemini (Google)?", default=False):
        return

    _panel(GOOGLE_OAUTH_INFO, title="Option 1")
    _panel(GEMINI_API_KEY_INFO, title="Option 2")

    choice = _input("Choose [1] Google OAuth or [2] API Key").strip()

    if choice == "1":
        from .providers.gemini import _has_google_oauth_credentials

        _print("\n  Follow the steps above to create your Google Cloud OAuth credentials.")
        _print("  Place client_secret.json at: ~/.config/iclaw/client_secret.json\n")

        if _has_google_oauth_credentials():
            _print("  [green]client_secret.json found![/green]" if _has_rich else "  client_secret.json found!")
        else:
            _print("  [yellow]client_secret.json not found yet.[/yellow]" if _has_rich else "  client_secret.json not found yet.")
            if not _confirm("  Continue anyway (you can add it later)?"):
                return

        config = ProviderConfig(
            provider_id=ProviderID.GEMINI,
            auth_mode=AuthMode.GOOGLE_OAUTH,
            enabled=True,
        )
    else:
        _print("  Get a key from: https://aistudio.google.com/apikey\n")
        key = _input("Enter your GEMINI_API_KEY (or press enter for env var)")
        config = ProviderConfig(
            provider_id=ProviderID.GEMINI,
            auth_mode=AuthMode.GEMINI_API_KEY,
            api_key=key if key.strip() else None,
            enabled=True,
        )

    registry.providers[ProviderID.GEMINI].configure(config)


def _select_active_provider(registry: ProviderRegistry) -> None:
    configured = registry.configured_providers()
    if len(configured) == 1:
        registry.set_active(configured[0].id)
        _print(f"\nActive provider: {configured[0].display_name}")
        return

    _print("\n[bold]Select your default provider:[/bold]" if _has_rich else "\nSelect your default provider:")
    for i, p in enumerate(configured, 1):
        _print(f"  [{i}] {p.display_name} — {p.status_line()}")

    choice = _input("Choice").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(configured):
            registry.set_active(configured[idx].id)
    except ValueError:
        registry.set_active(configured[0].id)


def _setup_cycling(registry: ProviderRegistry) -> None:
    configured = registry.configured_providers()
    if len(configured) < 2:
        return

    _print("\n[bold]Provider Cycling[/bold]" if _has_rich else "\nProvider Cycling")
    _print("When enabled, if the current provider hits a rate limit,")
    _print("iclaw automatically switches to the next configured provider.")
    _print("(2 rate limits within 5 minutes marks a provider as exhausted for the day.)\n")

    if _confirm("Enable provider cycling?", default=True):
        registry.enable_cycling()
        _print("  Cycle order: " + " -> ".join(p.display_name for p in configured))
