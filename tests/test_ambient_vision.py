from __future__ import annotations

import sys
import types

import pytest

from assistant.ambient_mode import AmbientMode
from vision.vision_service import VisionService


def test_ambient_mode_is_disabled_until_an_approved_signal_is_enabled():
    ambient = AmbientMode()

    decision = ambient.evaluate({"focused_minutes": 120})

    assert not ambient.enabled
    assert decision.action == "no_action"
    assert decision.reason == "ambient_mode_disabled"
    with pytest.raises(ValueError):
        ambient.enable(permissions={"microphone"})


def test_ambient_mode_respects_relevance_interruption_and_cooldown():
    now = [100.0]
    ambient = AmbientMode(clock=lambda: now[0])
    ambient.enable(permissions={"focused_work_timer"})

    assert ambient.evaluate({"focused_minutes": 89}).reason == "not_relevant"
    assert ambient.evaluate(
        {"focused_minutes": 100, "user_is_speaking": True}
    ).reason == "interruption_or_speech"
    first = ambient.evaluate({"focused_minutes": 100})
    assert first.action == "proactive_response"
    assert ambient.evaluate({"focused_minutes": 100}).reason == "signal_already_handled"

    ambient.evaluate({"focused_minutes": 0})
    now[0] += 60
    assert ambient.evaluate({"focused_minutes": 100}).reason == "cooldown"
    ambient.disable()
    assert ambient.evaluate({"focused_minutes": 120}).reason == "ambient_mode_disabled"


def test_vision_requires_consent_and_only_reports_local_aggregate_results(monkeypatch):
    class Capture:
        def __init__(self):
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            return True, object()

        def release(self):
            self.released = True

    class Classifier:
        def empty(self):
            return False

        def detectMultiScale(self, *_args, **_kwargs):
            return [(1, 2, 3, 4), (5, 6, 7, 8)]

    capture = Capture()
    cv2 = types.SimpleNamespace(
        VideoCapture=lambda _index: capture,
        CascadeClassifier=lambda _path: Classifier(),
        data=types.SimpleNamespace(haarcascades="local-models"),
        COLOR_BGR2GRAY=0,
        cvtColor=lambda _frame, _mode: "gray-frame",
    )
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    vision = VisionService()

    with pytest.raises(PermissionError):
        vision.start()
    assert not vision.is_active
    assert vision.start(consent=True)
    result = vision.analyze_scene()

    assert result["face_count"] == 2
    assert result["user_identity"] == "not_recognized"
    assert result["emotion"] == "unknown"
    assert result["emotion_confidence"] == 0.0
    vision.stop()
    assert capture.released
    assert not vision.is_active


def test_vision_releases_a_camera_that_cannot_be_opened(monkeypatch):
    class Capture:
        released = False

        def isOpened(self):
            return False

        def release(self):
            self.released = True

    capture = Capture()
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        types.SimpleNamespace(
            VideoCapture=lambda _index: capture,
            CascadeClassifier=lambda _path: None,
            data=types.SimpleNamespace(haarcascades="local-models"),
        ),
    )
    vision = VisionService()

    assert not vision.start(consent=True)
    assert capture.released
    assert not vision.is_active
    assert vision.last_error == "The selected camera could not be opened."


def test_runtime_construction_does_not_activate_sensors_or_ambient_mode():
    from core.aria_runtime import AriaRuntime

    runtime = AriaRuntime()
    try:
        assert not runtime.vision.is_active
        assert not runtime.ambient.enabled
    finally:
        runtime.stop()
