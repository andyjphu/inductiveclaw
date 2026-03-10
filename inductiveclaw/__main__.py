"""CLI entrypoint for InductiveClaw."""

from __future__ import annotations

import argparse
import sys

import anyio

from .config import ClawConfig
from .providers import ProviderRegistry
from .setup import run_setup


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="iclaw",
        description="InductiveClaw — Autonomous iterative coding agent",
    )

    parser.add_argument("-g", "--goal", default=None, help="What to build (omit for interactive mode)")
    parser.add_argument("--setup", action="store_true", help="Run guided provider setup")

    proj = parser.add_argument_group("project")
    proj.add_argument("-p", "--project", default=None, help="Project directory (default: . for interactive, ./project for autonomous)")
    proj.add_argument("-m", "--model", default=None, help="Model override")

    ctrl = parser.add_argument_group("iteration control (autonomous mode)")
    ctrl.add_argument("-t", "--threshold", type=int, default=8, help="Quality threshold 1-10 (default: 8)")
    ctrl.add_argument("--max-iterations", type=int, default=100, help="Max outer loop iterations (default: 100)")
    ctrl.add_argument("--eval-frequency", type=int, default=3, help="Evaluate every N iterations (default: 3)")

    vis = parser.add_argument_group("visual")
    vis.add_argument("--no-screenshot", action="store_true", help="Disable screenshot evaluation")
    vis.add_argument("--port", type=int, default=3000, help="Dev server port (default: 3000)")
    vis.add_argument("--dev-cmd", default=None, help="Dev server command (auto-detected if omitted)")

    inter = parser.add_argument_group("interactive mode")
    inter.add_argument("--no-auto", action="store_true", help="Disable auto-continue (agent stops after each turn)")

    out = parser.add_argument_group("output")
    out.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    out.add_argument("-v", "--verbose", action="store_true", help="Full agent output")

    return parser.parse_args(argv)


def _ensure_provider(registry: ProviderRegistry) -> bool:
    """Ensure at least one provider is configured. Returns True if ready."""
    # Try loading saved config
    if registry.load_config():
        if registry.active and registry.active.is_configured():
            return True

    # Try auto-detecting Anthropic
    registry.auto_detect()
    if registry.configured_providers():
        # If only one, set it active
        configured = registry.configured_providers()
        if len(configured) == 1 and registry.active_id is None:
            registry.set_active(configured[0].id)
        if registry.active and registry.active.is_configured():
            return True

    # Need setup
    return False


def _warn_no_sandbox(cwd: str) -> None:
    """Warn user that no sandbox directory is set and cwd will be used."""
    from pathlib import Path
    resolved = Path(cwd).resolve()

    # Count files that could be affected
    files = list(resolved.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    dirs = [d for d in resolved.iterdir() if d.is_dir() and not d.name.startswith(".")]
    dir_names = ", ".join(sorted(d.name for d in dirs)[:8])
    if len(dirs) > 8:
        dir_names += f", ... (+{len(dirs) - 8} more)"

    print(
        f"\033[33m"
        f"  Warning: No sandbox directory set (--project / -p flag).\n"
        f"  Agent will use current directory as sandbox: {resolved}\n"
        f"  Potentially affected: {file_count} files"
        + (f" in [{dir_names}]" if dir_names else "")
        + f"\n"
        f"  To isolate, use: iclaw -p ./sandbox\n"
        f"\033[0m",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    registry = ProviderRegistry()

    # --setup: run guided setup and exit
    if args.setup:
        _ensure_provider(registry)  # load existing config first
        run_setup(registry)
        return

    # Ensure we have a provider
    if not _ensure_provider(registry):
        print("No provider configured. Running setup...\n", file=sys.stderr)
        run_setup(registry)
        if not registry.active or not registry.active.is_configured():
            print("Setup incomplete. Run: iclaw --setup", file=sys.stderr)
            sys.exit(1)

    if args.goal:
        # Autonomous mode
        from .agent import run

        project_dir = args.project or "./project"
        config = ClawConfig(
            project_dir=project_dir,
            goal=args.goal,
            model=args.model,
            quality_threshold=args.threshold,
            max_iterations=args.max_iterations,
            eval_frequency=args.eval_frequency,
            auto_screenshot=not args.no_screenshot,
            screenshot_port=args.port,
            dev_server_cmd=args.dev_cmd,
            verbose=not args.quiet and args.verbose,
        )
        anyio.run(run, config, registry)
    else:
        # Interactive mode
        from pathlib import Path
        from .interactive import run_interactive

        if args.project:
            cwd = args.project
            Path(cwd).mkdir(parents=True, exist_ok=True)
        else:
            cwd = "."
            _warn_no_sandbox(cwd)
        try:
            anyio.run(run_interactive, registry, cwd, args.model, not args.no_auto)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
