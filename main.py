import sys
import os
import argparse

# Add the project root to sys.path to ensure absolute imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main(argv=None):
    parser = argparse.ArgumentParser(description="ARIA personal assistant")
    launch_mode = parser.add_mutually_exclusive_group()
    launch_mode.add_argument(
        "--demo",
        action="store_true",
        help="launch the Tkinter ARIA interface (the default)",
    )
    launch_mode.add_argument(
        "--cli",
        action="store_true",
        help="launch the terminal interface",
    )
    launch_mode.add_argument(
        "--web",
        action="store_true",
        help="launch the local browser interface",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="local browser interface port (default: 8765)",
    )
    args = parser.parse_args(argv)
    if args.web:
        from web.server import start_web_server

        return start_web_server(args.port)
    if not args.cli:
        try:
            from ui.neuron_demo import launch_demo

            launch_demo()
        except Exception as error:
            print(
                "ARIA's desktop interface could not start "
                f"({type(error).__name__}). Check Tkinter, UI dependencies, "
                "and that a desktop session is available.",
                file=sys.stderr,
            )
            return 1
        return 0

    from core.aria_core import AriaCore

    aria = AriaCore()
    aria.run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
