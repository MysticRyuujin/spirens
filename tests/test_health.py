"""Tests for spirens.commands.health internals."""

from __future__ import annotations

from spirens.commands.health import HealthReport


class TestHealthReport:
    def test_all_passed_true(self) -> None:
        report = HealthReport()
        report.add("check1", True, "ok")
        report.add("check2", True, "ok")
        assert report.all_passed is True

    def test_all_passed_false(self) -> None:
        report = HealthReport()
        report.add("check1", True, "ok")
        report.add("check2", False, "fail")
        assert report.all_passed is False

    def test_to_dict(self) -> None:
        report = HealthReport()
        report.add("check1", True, "200")
        data = report.to_dict()
        assert len(data) == 1
        assert data[0]["name"] == "check1"
        assert data[0]["passed"] is True
        assert data[0]["detail"] == "200"

    def test_empty_report_passes(self) -> None:
        report = HealthReport()
        assert report.all_passed is True
