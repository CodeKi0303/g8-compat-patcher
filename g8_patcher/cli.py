"""Command line entry point; no subcommand opens the desktop interface."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import PatcherError, build_package, list_profiles
from .network import download_original


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="g8-patcher",
        description="Download or select the pinned G8 original, then create a local update ZIP.",
    )
    command.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = command.add_subparsers(dest="command")
    subcommands.add_parser("gui", help="Open the desktop interface (also the default).")
    subcommands.add_parser("profiles", help="List supported profiles as JSON.")
    build = subcommands.add_parser("build", help="Create an update ZIP without writing to a controller.")
    sources = build.add_mutually_exclusive_group(required=True)
    sources.add_argument("--source", type=Path, metavar="ORIGINAL_ZIP", help="Select an existing original ZIP.")
    sources.add_argument("--download", action="store_true", help="Download the pinned original from GameSir.")
    build.add_argument("--profile", default="kishi-xbox", metavar="PROFILE", help="Profile ID (default: kishi-xbox).")
    build.add_argument("--output-dir", type=Path, required=True, metavar="DIRECTORY", help="Folder for newly generated files.")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in (None, "gui"):
            from .gui import run

            run()
            return 0
        if args.command == "profiles":
            print(json.dumps(list_profiles(), ensure_ascii=True, indent=2))
            return 0
        available = {profile["id"] for profile in list_profiles()}
        if args.profile not in available:
            raise PatcherError(f"Unknown profile: {args.profile}. Use 'profiles' to list supported IDs.")
        output = args.output_dir.expanduser().resolve()
        source = (
            download_original(output / "originals")
            if args.download
            else args.source.expanduser().resolve()
        )
        result = build_package(source, output, args.profile)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (PatcherError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
