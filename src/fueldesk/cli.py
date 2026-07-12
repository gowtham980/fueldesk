"""Console entry point: fueldesk serve | version."""

from __future__ import annotations

import argparse
import sys

from fueldesk import __version__
from fueldesk.config import DEFAULT_HOST, DEFAULT_PORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fueldesk",
        description="Local-first Personal Fuel & Training Protocol Desk",
    )
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Start the local web UI")
    serve_p.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default {DEFAULT_HOST})")
    serve_p.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default {DEFAULT_PORT})"
    )
    serve_p.add_argument("--reload", action="store_true", help="Auto-reload (dev)")

    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "serve":
        import uvicorn

        from fueldesk.web.app import create_app

        app = create_app()
        print(f"fueldesk v{__version__} → http://{args.host}:{args.port}")
        print("Educational planning tool — not medical advice.")
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload, log_level="info")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
