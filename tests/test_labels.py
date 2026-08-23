from docencia_tools.labels import desired_labels, reconcile_labels


def test_late_reviewable_delivery_goes_to_professor():
    labels = desired_labels({"punctuality": "late", "reviewable": True, "current_errors": []})
    assert labels == {"entrega:tarde", "revision:profesor"}


def test_corrected_errors_are_removed_and_historical_late_is_preserved():
    current = {"entrega:tarde", "revision:no-revisable", "error:titulo", "tema:edo"}
    desired = desired_labels({"punctuality": "late", "reviewable": True, "current_errors": []})
    add, remove = reconcile_labels(current, desired)
    assert add == {"revision:profesor"}
    assert remove == {"revision:no-revisable", "error:titulo"}
    assert "entrega:tarde" not in remove
