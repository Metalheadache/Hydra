"""
Entry point: python -m hydra

Starts the Hydra API server.
"""
from hydra.server import start_server

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hydra API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()
    start_server(host=args.host, port=args.port)
