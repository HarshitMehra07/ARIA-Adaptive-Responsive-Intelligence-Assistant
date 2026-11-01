import sys
import types

import main


def test_default_startup_launches_existing_desktop_ui(monkeypatch):
    calls = []
    ui_module = types.ModuleType("ui.neuron_demo")
    ui_module.launch_demo = lambda: calls.append("launch")
    monkeypatch.setitem(sys.modules, "ui.neuron_demo", ui_module)

    assert main.main([]) == 0
    assert calls == ["launch"]


def test_demo_alias_uses_same_ui_launcher(monkeypatch):
    calls = []
    ui_module = types.ModuleType("ui.neuron_demo")
    ui_module.launch_demo = lambda: calls.append("launch")
    monkeypatch.setitem(sys.modules, "ui.neuron_demo", ui_module)

    assert main.main(["--demo"]) == 0
    assert calls == ["launch"]


def test_cli_option_preserves_terminal_startup(monkeypatch):
    calls = []
    core_module = types.ModuleType("core.aria_core")

    class FakeAria:
        def run(self):
            calls.append("run")

    core_module.AriaCore = FakeAria
    monkeypatch.setitem(sys.modules, "core.aria_core", core_module)

    assert main.main(["--cli"]) == 0
    assert calls == ["run"]


def test_web_option_uses_local_web_launcher_and_forwards_port(monkeypatch):
    calls = []
    web_module = types.ModuleType("web.server")
    web_module.start_web_server = lambda port: calls.append(port) or 0
    monkeypatch.setitem(sys.modules, "web.server", web_module)

    assert main.main(["--web", "--port", "9001"]) == 0
    assert calls == [9001]


def test_ui_startup_failure_is_reported_with_nonzero_status(monkeypatch, capsys):
    ui_module = types.ModuleType("ui.neuron_demo")

    def fail_startup():
        raise RuntimeError("implementation details")

    ui_module.launch_demo = fail_startup
    monkeypatch.setitem(sys.modules, "ui.neuron_demo", ui_module)

    assert main.main([]) == 1
    stderr = capsys.readouterr().err
    assert "desktop interface could not start (RuntimeError)" in stderr
    assert "implementation details" not in stderr
