"""Metrics display: only the visible tab is updated, only changed widgets touched."""

from __future__ import annotations

import tkinter as tk

import pytest

from src.analysis.tiers.features import FastFeatures, MediumFeatures


@pytest.fixture
def display():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    from src.gui.metrics_display import RealTimeMetricsDisplay

    widget = RealTimeMetricsDisplay(root)
    widget.pack()
    root.update()
    yield widget
    root.destroy()


def _features(raw: float, bass: float) -> tuple[FastFeatures, MediumFeatures]:
    fast = FastFeatures(timestamp_s=1.0, onset_detected=False, onset_strength=0.0, is_percussive_peak=False,
                        percussive_peak_strength=0.0, raw_energy=raw)
    medium = MediumFeatures(timestamp_s=1.0, bass_energy=bass, mid_energy=0.0, high_energy=0.0,
                            bass_energy_delta=0.0, overall_energy_delta=0.0)
    return fast, medium


def test_only_visible_tab_updates_and_switching_tabs_refreshes(display) -> None:
    fast, medium = _features(raw=0.5, bass=0.25)
    display.update_features(fast, medium, None)
    display.update()  # runs the scheduled refresh
    assert display.value_labels["fast_raw_energy"].cget("text") == "0.500"
    assert display.value_labels["medium_bass"].cget("text") != "0.250"  # hidden tab untouched

    display.notebook.select(display.tabs["medium"])
    display.update()
    assert display.value_labels["medium_bass"].cget("text") == "0.250"


def test_unchanged_values_do_not_touch_widgets(display) -> None:
    fast, medium = _features(raw=0.5, bass=0.25)
    display.update_features(fast, medium, None)
    display.update()

    calls: list[dict] = []
    label = display.value_labels["fast_raw_energy"]
    original = label.config
    label.config = lambda **kw: (calls.append(kw), original(**kw))  # type: ignore[method-assign]
    display.update_features(fast, medium, None)
    display.update()
    assert calls == []

    fast.raw_energy = 0.75
    display.update_features(fast, medium, None)
    display.update()
    assert calls == [{"text": "0.750"}]
