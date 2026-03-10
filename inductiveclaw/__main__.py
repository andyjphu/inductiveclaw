"""CLI entrypoint for InductiveClaw."""

from __future__ import annotations

import argparse
import sys

import anyio

from . import auth
from .agent import run
from .auth import AuthError
from .config import ClawConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="iclaw",
        description="InductiveClaw — Autonomous iterative coding agent",
    )

    req = parser.add_argument_group("required")
    req.add_argument("-g", "--goal", required=True, help="What to build")

    proj = parser.add_argument_group("project")
    proj.add_argument("-p", "--project", default="./project", help="Project directory (default: ./project)")
    proj.add_argument("-m", "--model", default=None, help="Model override")

    ctrl = parser.add_argument_group("iteration control")
    ctrl.add_argument("-t", "--threshold", type=int, default=8, help="Quality threshold 1-10 (default: 8)")
    ctrl.add_argument("--max-iterations", type=int, default=100, help="Max outer loop iterations (default: 100)")
    ctrl.add_argument("--eval-frequency", type=int, default=3, help="Evaluate every N iterations (default: 3)")

    auth_grp = parser.add_argument_group("auth")
    auth_grp.add_argument("--use-api-key", action="store_true", help="Prefer API key over OAuth")
    auth_grp.add_argument("--api-key", default=None, help="Explicit API key")

    vis = parser.add_argument_group("visual")
    vis.add_argument("--no-screenshot", action="store_true", help="Disable screenshot evaluation")
    vis.add_argument("--port", type=int, default=3000, help="Dev server port (default: 3000)")
    vis.add_argument("--dev-cmd", default=None, help="Dev server command (auto-detected if omitted)")

    out = parser.add_argument_group("output")
    out.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    out.add_argument("-v", "--verbose", action="store_true", help="Full agent output")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    config = ClawConfig(
        project_dir=args.project,
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

    try:
        auth_result = auth.resolve(
            prefer_oauth=not args.use_api_key,
            force_api_key=args.api_key,
        )
    except AuthError as e:
        print(f"Authentication failed:\n{e}", file=sys.stderr)
        sys.exit(1)

    anyio.run(run, config, auth_result)


if __name__ == "__main__":
    main()
