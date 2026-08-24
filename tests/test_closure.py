from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from docencia_tools import cli
from docencia_tools.closure import close_delivery, consolidate_equivalent_states
from docencia_tools.config import Deadlines
from docencia_tools.errors import InfrastructureError


DELIVERY = "2026-08-23T23:59:00-06:00"
ON_TIME = "2026-08-23T22:00:00-06:00"
LATE = "2026-08-24T01:00:00-06:00"
EXTENDED_DEADLINE = "2026-08-24T00:05:00-06:00"
NOW = datetime.fromisoformat("2026-08-24T12:00:00-06:00")
STUDENTS = ("aline", "francisco", "leonardo")


def _state(
    student: str,
    *,
    first_complete: str | None = ON_TIME,
    reviewable: bool = True,
    activity: str = "clase_04",
    incoming_punctuality: str = "on_time",
    pull_request: int | None = None,
    head_sha: str | None = None,
    current_errors: list[str] | None = None,
) -> dict[str, object]:
    pr_number = pull_request if pull_request is not None else 1000 + sum(map(ord, student))
    return {
        "schema_version": 1,
        "activity": activity,
        "student": student,
        "pull_request": pr_number,
        "head_sha": head_sha if head_sha is not None else f"sha-{student}",
        "merge_base": f"base-{pr_number}",
        "trusted_ref": "trusted/main",
        "first_complete_at": (
            {
                "timestamp": first_complete,
                "sha": f"complete-{student}",
                "source": "git-history",
                "approximate": True,
            }
            if first_complete is not None
            else None
        ),
        "general_deadline": DELIVERY,
        "applied_deadline": DELIVERY,
        "punctuality": incoming_punctuality,
        "reviewable": reviewable,
        "current_errors": list(current_errors or []),
        "failures": [],
    }


def _three_states() -> list[dict[str, object]]:
    return [_state(student) for student in STUDENTS]


def _close(activity, states=None, *, private=None, seed="semilla", now=NOW):
    return close_delivery(
        activity,
        _three_states() if states is None else states,
        private=private,
        seed=seed,
        now=now,
    )


def _override(
    *,
    student="ana-perez",
    deadline=EXTENDED_DEADLINE,
    activity="clase_04",
    reason=None,
):
    override = {
        "activity": activity,
        "student": student,
        "deadline": deadline,
    }
    if reason is not None:
        override["reason"] = reason
    return override


def _write_state_directory(path: Path) -> Path:
    path.mkdir()
    for state in _three_states():
        student = str(state["student"])
        (path / f"{student}.json").write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )
    return path


def _write_private_extension(path: Path) -> Path:
    path.write_text(
        """deadline_overrides:
  - activity: clase_04
    student: estudiante-privado
    deadline: 2026-08-24T00:05:00-06:00
    reason: razon-que-no-debe-salir
""",
        encoding="utf-8",
    )
    return path


def _cli_closure_args(
    *,
    config_path: Path,
    states_path: Path,
    private_path: Path,
    output: Path,
    now: str,
    if_due: bool = False,
) -> list[str]:
    arguments = [
        "cerrar-entrega",
        "--config",
        str(config_path),
        "--estados",
        str(states_path),
        "--privada",
        str(private_path),
        "--semilla",
        "semilla-cli",
        "--ahora",
        now,
        "--salida",
        str(output),
    ]
    if if_due:
        arguments.append("--si-corresponde")
    return arguments


def test_three_eligible_states_produce_assignment_without_self_review(activity):
    result = _close(activity)

    assert result.eligible_participants == STUDENTS
    assert len(result.assignment.pairs) == 3
    assert all(reviewer != author for reviewer, author in result.assignment.pairs)


def test_same_seed_produces_exact_same_closure(activity):
    assert _close(activity).as_dict() == _close(activity).as_dict()


def test_late_reviewable_student_is_excluded(activity):
    states = _three_states() + [_state("tardia", first_complete=LATE)]
    result = _close(activity, states)

    assert "tardia" not in result.eligible_participants
    assert {"student": "tardia", "causes": ["late"]} in result.excluded
    assert all("tardia" not in pair for pair in result.assignment.pairs)


def test_on_time_not_reviewable_student_is_excluded(activity):
    states = _three_states() + [_state("no-revisable", reviewable=False)]
    result = _close(activity, states)

    assert "no-revisable" not in result.eligible_participants
    assert {"student": "no-revisable", "causes": ["not_reviewable"]} in result.excluded


def test_incomplete_student_is_excluded(activity):
    states = _three_states() + [_state("incompleta", first_complete=None)]
    result = _close(activity, states)

    assert "incompleta" not in result.eligible_participants
    assert {"student": "incompleta", "causes": ["incomplete"]} in result.excluded


def test_private_deadline_recalculates_late_delivery_as_on_time(activity):
    states = [
        _state(
            "antwone-ortega",
            first_complete="2026-08-24T00:00:52-06:00",
            incoming_punctuality="late",
        ),
        _state("francisco"),
        _state("leonardo"),
    ]
    private = {
        "deadline_overrides": [
            _override(student="antwone-ortega", reason="información reservada")
        ]
    }

    result = _close(activity, states, private=private)
    antwone = result.students["antwone-ortega"]

    assert antwone.punctuality == "on_time"
    assert antwone.exception_applied
    assert antwone.applied_deadline == EXTENDED_DEADLINE
    assert antwone.eligible_for_peer_review


def test_private_reason_never_appears_in_public_json(activity):
    secret = "motivo confidencial irrepetible"
    private = {
        "deadline_overrides": [
            {
                "activity": "clase_04",
                "student": "aline",
                "deadline": "2026-08-24T02:00:00-06:00",
                "reason": secret,
            }
        ]
    }

    public_json = json.dumps(_close(activity, private=private).as_dict(), ensure_ascii=False)

    assert secret not in public_json
    assert "reason" not in public_json


def test_exempt_from_reviewing_preserves_academic_eligibility(activity):
    result = _close(activity, private={"exempt_from_reviewing": ["aline"]})

    assert result.students["aline"].eligible_for_peer_review
    assert result.students["aline"].exempt_from_reviewing
    assert all(reviewer != "aline" for reviewer, _ in result.assignment.pairs)


def test_exempt_from_receiving_review_preserves_academic_eligibility(activity):
    result = _close(activity, private={"exempt_from_receiving_review": ["aline"]})

    assert result.students["aline"].eligible_for_peer_review
    assert result.students["aline"].exempt_from_receiving_review
    assert all(author != "aline" for _, author in result.assignment.pairs)


def test_hard_incompatibility_is_respected(activity):
    result = _close(
        activity,
        private={"incompatible_pairs": [["aline", "francisco"]]},
    )

    assert ("aline", "francisco") not in result.assignment.pairs
    assert ("francisco", "aline") not in result.assignment.pairs


def test_avoid_is_not_used_when_another_solution_exists(activity):
    result = _close(activity, private={"avoid": [["aline", "francisco"]]})

    assert ("aline", "francisco") not in result.assignment.pairs
    assert result.assignment.avoided_pairs_used == ()


def test_forced_assignment_is_respected(activity):
    result = _close(
        activity,
        private={"forced_assignments": [["aline", "francisco"]]},
    )

    assert ("aline", "francisco") in result.assignment.pairs


def test_equivalent_student_states_are_consolidated(activity):
    states = [
        _state("aline", pull_request=28, head_sha="same-sha"),
        _state("aline", pull_request=44, head_sha="same-sha"),
        _state("francisco"),
        _state("leonardo"),
    ]

    result = _close(activity, states)
    public_student = result.as_dict()["students"]["aline"]

    assert result.students["aline"].pull_request == 44
    assert result.students["aline"].observed_pull_requests == (28, 44)
    assert public_student["pull_request"] == 44
    assert public_student["observed_pull_requests"] == [28, 44]


def test_equivalent_states_use_oldest_first_complete(activity):
    old = _state(
        "aline",
        pull_request=37,
        head_sha="same-sha",
        first_complete="2026-08-23T22:00:00-06:00",
    )
    old["first_complete_at"]["observation"] = "preservada"
    new = _state(
        "aline",
        pull_request=59,
        head_sha="same-sha",
        first_complete="2026-08-24T08:00:00-06:00",
        incoming_punctuality="late",
    )

    consolidated = consolidate_equivalent_states(
        [new, old],
        activity="clase_04",
        timezone="America/Mexico_City",
    )["aline"]
    result = _close(activity, [old, new, _state("francisco"), _state("leonardo")])
    aline = result.students["aline"]

    assert consolidated["first_complete_at"] == old["first_complete_at"]
    assert aline.first_complete_at["timestamp"] == "2026-08-23T22:00:00-06:00"
    assert aline.first_complete_at["observation"] == "preservada"
    assert aline.punctuality == "on_time"
    assert aline.eligible_for_peer_review


def test_equivalent_states_use_only_canonical_current_state(activity):
    old = _state(
        "aline",
        pull_request=37,
        head_sha="same-sha",
        reviewable=True,
        current_errors=["error:rama"],
    )
    old["failures"] = [{"code": "error:rama"}]
    new = _state(
        "aline",
        pull_request=59,
        head_sha="same-sha",
        reviewable=False,
        current_errors=["error:base"],
    )
    new["failures"] = [{"code": "error:base"}]

    consolidated = consolidate_equivalent_states(
        [old, new],
        activity="clase_04",
        timezone="America/Mexico_City",
    )["aline"]
    result = _close(activity, [old, new, _state("francisco"), _state("leonardo")])

    assert consolidated["reviewable"] is False
    assert consolidated["current_errors"] == ["error:base"]
    assert consolidated["failures"] == [{"code": "error:base"}]
    assert consolidated["merge_base"] == new["merge_base"]
    assert result.students["aline"].reviewable is False
    assert not result.students["aline"].eligible_for_peer_review


def test_equivalent_null_and_complete_states_keep_complete_observation(activity):
    incomplete = _state(
        "aline",
        pull_request=28,
        head_sha="same-sha",
        first_complete=None,
    )
    complete = _state(
        "aline",
        pull_request=44,
        head_sha="same-sha",
        first_complete=ON_TIME,
    )

    result = _close(
        activity,
        [incomplete, complete, _state("francisco"), _state("leonardo")],
    )

    assert result.students["aline"].first_complete_at is not None
    assert result.students["aline"].punctuality == "on_time"


def test_same_student_with_different_head_shas_fails_clearly(activity):
    states = _three_states() + [
        _state("aline", pull_request=2000, head_sha="different-sha")
    ]

    with pytest.raises(InfrastructureError, match="ambigua.*head_sha distintos"):
        _close(activity, states)


def test_three_equivalent_pull_requests_are_consolidated(activity):
    equivalent = [
        _state("aline", pull_request=number, head_sha="same-sha")
        for number in (28, 44, 61)
    ]

    result = _close(activity, [*equivalent, _state("francisco"), _state("leonardo")])

    assert result.students["aline"].pull_request == 61
    assert result.students["aline"].observed_pull_requests == (28, 44, 61)


def test_equivalent_state_order_does_not_change_closure(activity):
    states = [
        _state("aline", pull_request=28, head_sha="same-sha", first_complete=ON_TIME),
        _state("aline", pull_request=44, head_sha="same-sha", first_complete=LATE),
        _state("francisco"),
        _state("leonardo"),
    ]

    assert _close(activity, states).as_dict() == _close(activity, reversed(states)).as_dict()


def test_single_pull_request_keeps_normal_behavior(activity):
    state = _state("aline", pull_request=28, head_sha="only-sha")

    result = _close(activity, [state, _state("francisco"), _state("leonardo")])

    assert result.students["aline"].pull_request == 28
    assert result.students["aline"].observed_pull_requests == (28,)
    assert result.students["aline"].first_complete_at["timestamp"] == ON_TIME


@pytest.mark.parametrize(
    ("pull_request", "head_sha", "message"),
    [
        (0, "sha", "pull_request entero válido"),
        (True, "sha", "pull_request entero válido"),
        ("28", "sha", "pull_request entero válido"),
        (28, "", "head_sha válido"),
        (28, None, "head_sha válido"),
    ],
)
def test_equivalent_state_identity_must_be_safe(
    activity,
    pull_request,
    head_sha,
    message,
):
    state = _state("aline")
    state["pull_request"] = pull_request
    state["head_sha"] = head_sha

    with pytest.raises(InfrastructureError, match=message):
        _close(activity, [state])


def test_private_reason_is_absent_from_ambiguous_equivalent_error(activity):
    secret = "razón privada que no debe aparecer"
    private = {
        "deadline_overrides": [
            _override(
                student="aline",
                deadline="2026-08-24T00:05:00-06:00",
                reason=secret,
            )
        ]
    }
    states = [
        _state("aline", pull_request=28, head_sha="sha-one"),
        _state("aline", pull_request=44, head_sha="sha-two"),
    ]

    with pytest.raises(InfrastructureError) as error:
        _close(activity, states, private=private)

    assert secret not in str(error.value)


def test_state_from_another_activity_fails(activity):
    states = _three_states()
    states[1] = _state("francisco", activity="clase_03")

    with pytest.raises(InfrastructureError, match="clase_03.*clase_04"):
        _close(activity, states)


def test_closure_before_delivery_deadline_fails(activity):
    before = datetime.fromisoformat("2026-08-23T23:58:59-06:00")

    with pytest.raises(InfrastructureError, match="ventana válida"):
        _close(activity, now=before)


def test_active_override_rejects_closure_before_its_deadline(activity):
    private = {"deadline_overrides": [_override()]}
    now = datetime.fromisoformat("2026-08-24T00:01:00-06:00")

    with pytest.raises(InfrastructureError, match="ventana válida.*00:05:00"):
        _close(activity, private=private, now=now)


def test_active_override_rejects_closure_exactly_at_its_deadline(activity):
    private = {"deadline_overrides": [_override()]}
    now = datetime.fromisoformat(EXTENDED_DEADLINE)

    with pytest.raises(InfrastructureError, match="inclusive"):
        _close(activity, private=private, now=now)


def test_closure_is_allowed_one_second_after_effective_deadline(activity):
    private = {"deadline_overrides": [_override()]}
    now = datetime.fromisoformat("2026-08-24T00:05:01-06:00")

    result = _close(activity, private=private, now=now)

    assert result.effective_closure_deadline == EXTENDED_DEADLINE
    assert result.eligible_participants == STUDENTS


def test_active_override_without_student_state_still_blocks_closure(activity):
    private = {
        "deadline_overrides": [
            _override(student="sin-estado", deadline="2026-08-24T00:30:00-06:00")
        ]
    }
    now = datetime.fromisoformat("2026-08-24T00:10:00-06:00")

    with pytest.raises(InfrastructureError, match="00:30:00"):
        _close(activity, private=private, now=now)


def test_expired_override_without_state_does_not_change_participants(activity):
    private = {
        "deadline_overrides": [
            _override(student="sin-estado", deadline="2026-08-24T00:30:00-06:00")
        ]
    }
    now = datetime.fromisoformat("2026-08-24T00:30:01-06:00")

    result = _close(activity, private=private, now=now)

    assert result.eligible_participants == STUDENTS
    assert "sin-estado" not in result.students
    assert result.effective_closure_deadline == "2026-08-24T00:30:00-06:00"


def test_effective_closure_deadline_is_latest_activity_override(activity):
    private = {
        "deadline_overrides": [
            _override(student="primera", deadline="2026-08-24T00:05:00-06:00"),
            _override(student="ultima", deadline="2026-08-24T00:30:00-06:00"),
            _override(student="intermedia", deadline="2026-08-24T00:15:00-06:00"),
        ]
    }

    with pytest.raises(InfrastructureError, match="00:30:00"):
        _close(
            activity,
            private=private,
            now=datetime.fromisoformat("2026-08-24T00:20:00-06:00"),
        )


def test_other_activity_overrides_do_not_delay_closure(activity):
    private = {
        "deadline_overrides": [
            _override(
                activity="clase_03",
                deadline="2026-09-30T23:59:00-06:00",
            )
        ]
    }
    now = datetime.fromisoformat("2026-08-24T00:00:01-06:00")

    result = _close(activity, private=private, now=now)

    assert result.effective_closure_deadline == DELIVERY


def test_private_reason_is_absent_from_closure_error_result_and_json(activity):
    secret = "motivo ultraprivado de la prórroga"
    private = {"deadline_overrides": [_override(reason=secret)]}

    with pytest.raises(InfrastructureError) as error:
        _close(
            activity,
            private=private,
            now=datetime.fromisoformat("2026-08-24T00:01:00-06:00"),
        )
    assert secret not in str(error.value)
    assert "ana-perez" not in str(error.value)

    result = _close(
        activity,
        private=private,
        now=datetime.fromisoformat("2026-08-24T00:05:01-06:00"),
    )
    assert secret not in repr(result)
    assert secret not in json.dumps(result.as_dict(), ensure_ascii=False)


def test_disabled_activity_cannot_be_closed(activity):
    disabled = replace(activity, enabled=False)

    with pytest.raises(InfrastructureError, match="no está habilitada"):
        _close(disabled)


def test_activity_without_delivery_deadline_cannot_be_closed(activity):
    without_delivery = replace(
        activity,
        deadlines=Deadlines(
            delivery=None,
            review=activity.deadlines.review,
            reply=activity.deadlines.reply,
        ),
    )

    with pytest.raises(InfrastructureError, match="no tiene delivery deadline"):
        _close(without_delivery)


def test_cli_writes_valid_closure_json(activity, config_path: Path, tmp_path: Path):
    states_directory = tmp_path / "estados"
    states_directory.mkdir()
    for state in _three_states():
        student = str(state["student"])
        (states_directory / f"{student}.json").write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )
    output = tmp_path / "cierre.json"

    exit_code = cli.main(
        [
            "cerrar-entrega",
            "--config",
            str(config_path),
            "--estados",
            str(states_directory),
            "--semilla",
            "semilla-cli",
            "--ahora",
            NOW.isoformat(),
            "--salida",
            str(output),
        ]
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert document["schema_version"] == 1
    assert document["activity"] == "clase_04"
    assert document["effective_closure_deadline"] == DELIVERY
    assert document["eligible_participants"] == list(STUDENTS)
    assert len(document["assignment"]["pairs"]) == 3


def test_cli_active_native_yaml_override_fails_without_writing_output(
    config_path: Path,
    tmp_path: Path,
    capsys,
):
    states_directory = tmp_path / "estados"
    states_directory.mkdir()
    for state in _three_states():
        student = str(state["student"])
        (states_directory / f"{student}.json").write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )
    private_path = tmp_path / "private.yml"
    private_path.write_text(
        """deadline_overrides:
  - activity: clase_04
    student: estudiante-privado
    deadline: 2026-08-24T00:05:00-06:00
    reason: razon-que-no-debe-salir
""",
        encoding="utf-8",
    )
    output = tmp_path / "cierre.json"

    exit_code = cli.main(
        [
            "cerrar-entrega",
            "--config",
            str(config_path),
            "--estados",
            str(states_directory),
            "--privada",
            str(private_path),
            "--semilla",
            "semilla-cli",
            "--ahora",
            "2026-08-24T00:01:00-06:00",
            "--salida",
            str(output),
        ]
    )

    error = capsys.readouterr().err
    assert exit_code != 0
    assert "ventana válida" in error
    assert "estudiante-privado" not in error
    assert "razon-que-no-debe-salir" not in error
    assert not output.exists()


def test_cli_if_due_before_deadline_returns_zero(config_path: Path, tmp_path: Path, capsys):
    private_path = _write_private_extension(tmp_path / "private.yml")
    output = tmp_path / "cierre.json"

    exit_code = cli.main(
        _cli_closure_args(
            config_path=config_path,
            states_path=tmp_path / "estados-aun-inexistentes",
            private_path=private_path,
            output=output,
            now="2026-08-24T00:01:00-06:00",
            if_due=True,
        )
    )
    capsys.readouterr()

    assert exit_code == 0


def test_cli_if_due_before_deadline_does_not_create_output(config_path: Path, tmp_path: Path, capsys):
    private_path = _write_private_extension(tmp_path / "private.yml")
    output = tmp_path / "cierre.json"

    cli.main(
        _cli_closure_args(
            config_path=config_path,
            states_path=tmp_path / "estados-aun-inexistentes",
            private_path=private_path,
            output=output,
            now="2026-08-24T00:01:00-06:00",
            if_due=True,
        )
    )
    capsys.readouterr()

    assert not output.exists()


def test_cli_if_due_pending_message_does_not_reveal_private_data(
    config_path: Path,
    tmp_path: Path,
    capsys,
):
    private_path = _write_private_extension(tmp_path / "private.yml")

    cli.main(
        _cli_closure_args(
            config_path=config_path,
            states_path=tmp_path / "estados-aun-inexistentes",
            private_path=private_path,
            output=tmp_path / "cierre.json",
            now="2026-08-24T00:01:00-06:00",
            if_due=True,
        )
    )

    message = capsys.readouterr().out
    assert message.strip() == "Cierre pendiente: todavía existe una ventana válida de entrega."
    assert "estudiante-privado" not in message
    assert "razon-que-no-debe-salir" not in message


def test_cli_if_due_exactly_at_deadline_is_noop(config_path: Path, tmp_path: Path, capsys):
    private_path = _write_private_extension(tmp_path / "private.yml")
    output = tmp_path / "cierre.json"

    exit_code = cli.main(
        _cli_closure_args(
            config_path=config_path,
            states_path=tmp_path / "estados-aun-inexistentes",
            private_path=private_path,
            output=output,
            now=EXTENDED_DEADLINE,
            if_due=True,
        )
    )
    capsys.readouterr()

    assert exit_code == 0
    assert not output.exists()


def test_cli_if_due_after_deadline_writes_normal_closure(config_path: Path, tmp_path: Path, capsys):
    states_path = _write_state_directory(tmp_path / "estados")
    private_path = _write_private_extension(tmp_path / "private.yml")
    output = tmp_path / "cierre.json"

    exit_code = cli.main(
        _cli_closure_args(
            config_path=config_path,
            states_path=states_path,
            private_path=private_path,
            output=output,
            now="2026-08-24T00:05:01-06:00",
            if_due=True,
        )
    )
    capsys.readouterr()

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["activity"] == "clase_04"


def test_cli_after_deadline_is_identical_with_or_without_if_due(
    config_path: Path,
    tmp_path: Path,
    capsys,
):
    states_path = _write_state_directory(tmp_path / "estados")
    private_path = _write_private_extension(tmp_path / "private.yml")
    strict_output = tmp_path / "estricto.json"
    noop_output = tmp_path / "si-corresponde.json"
    common = {
        "config_path": config_path,
        "states_path": states_path,
        "private_path": private_path,
        "now": "2026-08-24T00:05:01-06:00",
    }

    strict_exit = cli.main(
        _cli_closure_args(**common, output=strict_output)
    )
    noop_exit = cli.main(
        _cli_closure_args(**common, output=noop_output, if_due=True)
    )
    capsys.readouterr()

    assert strict_exit == noop_exit == 0
    assert strict_output.read_bytes() == noop_output.read_bytes()
