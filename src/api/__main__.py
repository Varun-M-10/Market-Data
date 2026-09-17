import argparse
import os
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run live market data web server.")
    parser.add_argument(
        "--source",
        choices=["mock", "nse", "dhan"],
        help="Override config data_source ('mock', 'nse', 'dhan')",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()

    if args.source:
        os.environ["DATA_SOURCE"] = args.source

    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )
