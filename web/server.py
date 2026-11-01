from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from web.app import app


HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def start_web_server(port: int = DEFAULT_PORT) -> int:
    if not 1 <= port <= 65_535:
        print("ARIA's browser port must be between 1 and 65535.", file=sys.stderr)
        return 1

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.bind((HOST, port))
        server_socket.listen(socket.SOMAXCONN)
        server_socket.setblocking(False)
    except OSError as error:
        server_socket.close()
        print(
            f"ARIA could not start at http://{HOST}:{port}/ because the local port is unavailable "
            f"({error}). Close the application using that port or run with --port <number>.",
            file=sys.stderr,
        )
        return 1

    url = f"http://{HOST}:{port}/"
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=HOST,
            port=port,
            log_level="info",
            access_log=False,
        )
    )
    print(f"ARIA browser interface: {url}", flush=True)

    def open_browser_when_ready() -> None:
        deadline = time.monotonic() + 10
        while not server.started and not server.should_exit and time.monotonic() < deadline:
            time.sleep(0.05)
        if server.started:
            webbrowser.open(url)

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    try:
        server.run(sockets=[server_socket])
        return 0
    except OSError as error:
        print(f"ARIA's local web server stopped unexpectedly ({type(error).__name__}).", file=sys.stderr)
        return 1
    finally:
        server_socket.close()
