from __future__ import annotations

import socket
import threading

import web.server as server_module


def test_server_binds_ipv4_loopback_and_opens_browser_after_startup(monkeypatch, capsys):
    opened = threading.Event()
    bound_addresses = []
    browser_urls = []
    server_instances = []

    class FakeSocket:
        def bind(self, address):
            bound_addresses.append(address)

        def listen(self, _backlog):
            pass

        def setblocking(self, _blocking):
            pass

        def close(self):
            pass

    class FakeConfig:
        def __init__(self, app, **kwargs):
            self.app = app
            self.kwargs = kwargs

    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.started = False
            self.should_exit = False
            server_instances.append(self)

        def run(self, *, sockets):
            assert len(sockets) == 1
            self.started = True

    monkeypatch.setattr(server_module.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(server_module.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(server_module.uvicorn, "Server", FakeServer)

    def open_browser(url):
        browser_urls.append(url)
        opened.set()
        return True

    monkeypatch.setattr(server_module.webbrowser, "open", open_browser)

    assert server_module.start_web_server(8765) == 0
    assert opened.wait(timeout=1)
    assert bound_addresses == [("127.0.0.1", 8765)]
    assert server_instances[0].config.kwargs["host"] == "127.0.0.1"
    assert browser_urls == ["http://127.0.0.1:8765/"]
    assert "http://127.0.0.1:8765/" in capsys.readouterr().out


def test_port_conflict_reports_local_alternative(capsys):
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    try:
        result = server_module.start_web_server(port)
    finally:
        occupied.close()

    assert result == 1
    error = capsys.readouterr().err
    assert "local port is unavailable" in error
    assert "--port <number>" in error


def test_server_rejects_non_tcp_port_numbers(capsys):
    assert server_module.start_web_server(65_536) == 1
    assert "between 1 and 65535" in capsys.readouterr().err
