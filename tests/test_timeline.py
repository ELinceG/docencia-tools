from datetime import timedelta

from docencia_tools.timeline import academic_phase


def test_python_decides_transitions_from_yaml(activity):
    assert academic_phase(activity, activity.deadlines.delivery - timedelta(seconds=1)) == "delivery"
    assert academic_phase(activity, activity.deadlines.delivery + timedelta(seconds=1)) == "review"
    assert academic_phase(activity, activity.deadlines.review + timedelta(seconds=1)) == "reply"
    assert academic_phase(activity, activity.deadlines.reply + timedelta(seconds=1)) == "closed"
