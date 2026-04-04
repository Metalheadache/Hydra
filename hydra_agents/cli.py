"""
hydra-agents CLI — entry point for the Hydra framework.

Usage:
    hydra-agents serve [--host HOST] [--port PORT] [--no-open]
    hydra-agents run "Your task here"
    hydra-agents --version
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser
import threading

from hydra_agents import __version__


def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    """Open browser after a short delay to let the server start."""
    import time
    time.sleep(delay)
    webbrowser.open(url)


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the Hydra web server."""
    import uvicorn

    if not args.no_open:
        url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"
        t = threading.Thread(target=_open_browser_delayed, args=(url,), daemon=True)
        t.start()

    uvicorn.run(
        "hydra_agents.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Run a task from the command line and print the result."""
    from hydra_agents import Hydra

    async def _run() -> None:
        hydra = Hydra()
        result = await hydra.run(args.task)
        print(result.get("output", ""))
        warnings = result.get("warnings", [])
        if warnings:
            print(f"\n⚠️  Warnings: {', '.join(warnings)}", file=sys.stderr)

    asyncio.run(_run())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hydra-agents",
        description="Hydra — Dynamic Multi-Agent Orchestration Framework",
    )
    parser.add_argument(
        "--version", "-V", action="version",
        version=f"hydra-agents {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the Hydra web server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    serve_parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")

    # run
    run_parser = subparsers.add_parser("run", help="Run a task from the command line")
    run_parser.add_argument("task", help="Task description")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
