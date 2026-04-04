"""
Report Generation Example
==========================

A more complex example demonstrating the full pipeline:
- 4-5 sub-tasks with dependencies
- Research + analysis + writing agents
- File generation (Markdown report)
- Full Brain → Agents → Post-Brain pipeline

Requirements:
    HYDRA_API_KEY=sk-ant-...
    HYDRA_DEFAULT_MODEL=anthropic/claude-sonnet-4-6
    HYDRA_SEARCH_API_KEY=<brave/tavily key>  # Optional but recommended for web search

Run:
    python examples/report_generation.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hydra_agents import Hydra, HydraConfig


async def main() -> None:
    config = HydraConfig(
        api_key=os.environ.get("HYDRA_API_KEY", ""),
        default_model=os.environ.get("HYDRA_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6"),
        brain_model=os.environ.get("HYDRA_BRAIN_MODEL", "anthropic/claude-sonnet-4-6"),
        post_brain_model=os.environ.get("HYDRA_POST_BRAIN_MODEL", "anthropic/claude-sonnet-4-6"),
        search_api_key=os.environ.get("HYDRA_SEARCH_API_KEY", ""),
        search_backend=os.environ.get("HYDRA_SEARCH_BACKEND", "brave"),
        max_concurrent_agents=5,
        per_agent_timeout_seconds=120,
        total_task_timeout_seconds=600,
        output_directory="./hydra_output/reports",
    )

    hydra = Hydra(config=config)

    task = """
    Analyze the AI agent platform market and produce a comprehensive strategy report.

    The report should cover:
    1. Market landscape — major players (LangChain, AutoGen, CrewAI, OpenAI Assistants API, etc.)
    2. Technical capabilities — what each platform can and cannot do
    3. Use case analysis — which domains are seeing the most adoption
    4. Competitive advantages — how they differentiate
    5. Strategic recommendations — for a startup building on agent infrastructure

    Deliverable: A structured Markdown report saved to disk (~1500 words).
    """

    print("=" * 70)
    print("HYDRA — Report Generation Example")
    print("=" * 70)
    print("Task: AI Agent Platform Market Strategy Report\n")
    print("This will run 4-5 specialized agents in a dependency graph...")
    print("(Research → Analysis → Writing → File generation)\n")

    result = await hydra.run(task)

    print("\n" + "=" * 70)
    print("SYNTHESIS COMPLETE")
    print("=" * 70)

    # Print first 2000 chars of the output
    output = result["output"]
    preview = output[:2000] + ("\n... [truncated]" if len(output) > 2000 else "")
    print(preview)

    if result["files_generated"]:
        print("\n📁 FILES GENERATED:")
        for f in result["files_generated"]:
            print(f"  - {f}")

    if result["warnings"]:
        print("\n⚠️  WARNINGS:")
        for w in result["warnings"]:
            print(f"  - {w}")

    summary = result["execution_summary"]
    print("\n📊 EXECUTION SUMMARY")
    print(f"  Agents: {summary['total_agents']} (✅ {summary['completed']}, ❌ {summary['failed']})")
    print(f"  Total tokens: {summary['total_tokens_used']:,}")
    print(f"  Wall-clock time: {summary['wall_clock_time_ms'] / 1000:.1f}s")
    print(f"  Files generated: {summary['files_generated']}")


if __name__ == "__main__":
    asyncio.run(main())
