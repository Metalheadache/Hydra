"""
Entry point: python -m hydra_agents

Starts the Hydra API server (or dispatches to CLI).
"""
from hydra_agents.cli import main

if __name__ == "__main__":
    main()
