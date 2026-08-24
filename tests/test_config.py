from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from docencia_tools.config import load_activity
from docencia_tools.errors import InfrastructureError
from docencia_tools.technical import write_requirements


def _write_deadlines(
    config_path: Path,
    *,
    delivery,
    review,
    reply,
    enabled: bool = True,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["enabled"] = enabled
    data["deadlines"] = {
        "delivery": delivery,
        "review": review,
        "reply": reply,
    }
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_loads_valid_config(activity):
    assert activity.activity == "clase_04"
    assert activity.deadlines.delivery.isoformat() == "2026-08-23T23:59:00-06:00"


def test_enabled_activity_requires_deadlines(config_path: Path):
    text = config_path.read_text(encoding="utf-8").replace("2026-08-23T23:59:00-06:00", "PENDIENTE")
    config_path.write_text(text, encoding="utf-8")
    with pytest.raises(InfrastructureError, match="obligatorio"):
        load_activity(config_path)


def test_loads_unquoted_yaml_timestamp_with_offset(config_path: Path):
    offset = timezone(timedelta(hours=-6))
    _write_deadlines(
        config_path,
        delivery=datetime(2026, 8, 15, 23, 59, tzinfo=offset),
        review=datetime(2026, 8, 18, 18, 59, tzinfo=offset),
        reply=datetime(2026, 8, 20, 17, 59, tzinfo=offset),
    )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw["deadlines"]["delivery"], datetime)
    config = load_activity(config_path)
    assert config.deadlines.delivery.isoformat() == "2026-08-15T23:59:00-06:00"


def test_loads_quoted_yaml_timestamp(config_path: Path):
    _write_deadlines(
        config_path,
        delivery="2026-08-15T23:59:00-06:00",
        review="2026-08-18T18:59:00-06:00",
        reply="2026-08-20T17:59:00-06:00",
    )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw["deadlines"]["delivery"], str)
    config = load_activity(config_path)
    assert config.deadlines.delivery.isoformat() == "2026-08-15T23:59:00-06:00"


def test_naive_yaml_datetime_uses_configured_timezone(config_path: Path):
    _write_deadlines(
        config_path,
        delivery=datetime(2026, 8, 15, 23, 59),
        review=datetime(2026, 8, 18, 18, 59),
        reply=datetime(2026, 8, 20, 17, 59),
    )
    config = load_activity(config_path)
    assert config.deadlines.delivery.tzinfo == ZoneInfo("America/Mexico_City")
    assert config.deadlines.delivery.isoformat() == "2026-08-15T23:59:00-06:00"


def test_pending_deadlines_are_allowed_when_disabled(config_path: Path):
    _write_deadlines(
        config_path,
        delivery="PENDIENTE",
        review="PENDIENTE",
        reply="PENDIENTE",
        enabled=False,
    )
    config = load_activity(config_path)
    assert config.deadlines.delivery is None
    assert config.deadlines.review is None
    assert config.deadlines.reply is None


def test_pending_deadline_fails_when_enabled(config_path: Path):
    _write_deadlines(
        config_path,
        delivery="PENDIENTE",
        review="2026-08-18T18:59:00-06:00",
        reply="2026-08-20T17:59:00-06:00",
    )
    with pytest.raises(InfrastructureError, match="obligatorio"):
        load_activity(config_path)


def test_yaml_date_without_time_is_rejected(config_path: Path):
    _write_deadlines(
        config_path,
        delivery=date(2026, 8, 15),
        review=datetime(2026, 8, 18, 18, 59),
        reply=datetime(2026, 8, 20, 17, 59),
    )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw["deadlines"]["delivery"], date)
    assert not isinstance(raw["deadlines"]["delivery"], datetime)
    with pytest.raises(InfrastructureError, match="timestamp ISO 8601"):
        load_activity(config_path)


def test_deadline_order_is_checked_for_native_yaml_datetimes(config_path: Path):
    _write_deadlines(
        config_path,
        delivery=datetime(2026, 8, 19, 23, 59),
        review=datetime(2026, 8, 18, 18, 59),
        reply=datetime(2026, 8, 20, 17, 59),
    )
    with pytest.raises(InfrastructureError, match="delivery <= review <= reply"):
        load_activity(config_path)


def test_requirements_are_materialized_from_trusted_config(activity, tmp_path: Path):
    object.__setattr__(activity.technical, "dependencies", ("numpy>=2", "PyYAML>=6,<7"))
    output = tmp_path / "requirements.txt"
    write_requirements(activity, output)
    assert output.read_text(encoding="utf-8") == "numpy>=2\nPyYAML>=6,<7\n"


def test_requirements_reject_shell_syntax(activity, tmp_path: Path):
    object.__setattr__(activity.technical, "dependencies", ("numpy; touch /tmp/x",))
    with pytest.raises(InfrastructureError, match="Dependencias inválidas"):
        write_requirements(activity, tmp_path / "requirements.txt")
