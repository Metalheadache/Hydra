"""
Simple Research Example
=======================

This example shows Hydra decomposing a research question into parallel
sub-tasks and synthesizing the results.

Requirements:
    HYDRA_API_KEY=sk-ant-...
    HYDRA_DEFAULT_MODEL=anthropic/claude-sonnet-4-6

Run:
    python examples/simple_research.py
"""

import asyncio
import os
import sys

# Allow running from the repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hydra_agents import Hydra, HydraConfig


async def main() -> None:
    # Configure via environment or directly
    config = HydraConfig(
        api_key=os.environ.get("HYDRA_API_KEY", ""),
        default_model=os.environ.get("HYDRA_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6"),
        brain_model=os.environ.get("HYDRA_BRAIN_MODEL", "anthropic/claude-sonnet-4-6"),
        post_brain_model=os.environ.get("HYDRA_POST_BRAIN_MODEL", "anthropic/claude-sonnet-4-6"),
        # Don't need web search for a simple in-context research task
        max_concurrent_agents=3,
        per_agent_timeout_seconds=90,
    )

    hydra = Hydra(config=config)

    task = (
        "Research the current state of large language models (LLMs) in 2024-2025. "
        "Cover: (1) major model releases and their capabilities, "
        "(2) key technical breakthroughs, "
        "(3) practical applications being built. "
        "Produce a concise 3-section summary."
    )

    print("=" * 60)
    print("HYDRA — Simple Research Example")
    print("=" * 60)
    print(f"Task: {task}\n")

    result = await hydra.run(task)

    print("\n" + "=" * 60)
    print("SYNTHESIS OUTPUT")
    print("=" * 60)
    print(result["output"])

    if result["warnings"]:
        print("\n⚠️  WARNINGS:")
        for w in result["warnings"]:
            print(f"  - {w}")

    summary = result["execution_summary"]
    print("\n📊 EXECUTION SUMMARY")
    print(f"  Agents: {summary['total_agents']} (✅ {summary['completed']}, ❌ {summary['failed']})")
    print(f"  Total tokens: {summary['total_tokens_used']:,}")
    print(f"  Wall-clock time: {summary['wall_clock_time_ms'] / 1000:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
