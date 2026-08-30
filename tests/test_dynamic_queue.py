from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

import database
from database import DatabaseManager
from services import cart_service, enroll_service


def _course(course_id: str, *, rank: int = 0, group: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=course_id,
        type="FANKC",
        name=f"课程 {course_id}",
        campus_code="01",
        campus_name="粤海校区",
        course_number=course_id,
        teaching_place="1-18周 星期一 1-2节 教学楼101",
        time_signature="1:1-2",
        priority_group=group,
        priority_rank=rank,
        auto_enabled=True,
        is_choose="",
        is_conflict="",
    )


@pytest.fixture(autouse=True)
def reset_worker_state():
    enroll_service._release_enroll_task()
    enroll_service._set_progress_finished()
    yield
    enroll_service._release_enroll_task()
    enroll_service._set_progress_finished()


def _wait_for_pause_acknowledgement(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if enroll_service.get_enroll_task_state()["pause_acknowledged"]:
            return
        time.sleep(0.01)
    raise AssertionError("worker did not acknowledge pause")


def test_running_queue_mutations_require_an_acknowledged_pause(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path / "dynamic.db"))
    monkeypatch.setattr(cart_service, "db", db)
    first = _course("first", rank=10)
    failed = _course("failed", rank=20)
    added = _course("added", rank=30)
    assert cart_service.add_course(first)["success"]
    assert cart_service.add_course(failed)["success"]
    assert cart_service.update_status(failed.id, database.STATUS_FAILED)
    assert enroll_service.reserve_enroll_task()
    initial_revision = enroll_service.get_enroll_task_state()["queue_revision"]

    blocked = enroll_service.add_cart_course(added)
    assert blocked["error_code"] == "ENROLL_TASK_NOT_PAUSED"
    assert enroll_service.pause_enroll_task()[0]
    pending = enroll_service.add_cart_course(added)
    assert pending["error_code"] == "ENROLL_TASK_PAUSE_PENDING"

    waiter_result: list[bool] = []
    waiter = threading.Thread(
        target=lambda: waiter_result.append(enroll_service._wait_until_resumed())
    )
    waiter.start()
    try:
        _wait_for_pause_acknowledgement()
        add_result = enroll_service.add_cart_course(added)
        preference_result = enroll_service.update_cart_course_preferences(
            first.id,
            priority_group="核心",
            priority_rank=1,
        )
        retry_result = enroll_service.retry_cart_course(failed.id)
        priority_result = enroll_service.update_cart_course_priorities(
            [(first.id, 1), (failed.id, 2), (added.id, 3)]
        )

        assert add_result["success"] is True
        assert preference_result["success"] is True
        assert retry_result["success"] is True
        assert priority_result["success"] is True
        assert priority_result["queue_revision"] == initial_revision + 4
        assert enroll_service.get_enroll_task_state()["pause_acknowledged"] is True
        assert enroll_service.resume_enroll_task()[0]
        waiter.join(timeout=2)
        assert waiter_result == [True]
    finally:
        enroll_service.stop_enroll_task()
        enroll_service._release_enroll_task()
        waiter.join(timeout=2)


def test_reconcile_adds_new_work_preserves_counters_and_removes_disabled_items(
    tmp_path,
    monkeypatch,
):
    db = DatabaseManager(str(tmp_path / "reconcile.db"))
    monkeypatch.setattr(cart_service, "db", db)
    first = _course("first", rank=20)
    added = _course("added", rank=10)
    assert cart_service.add_course(first)["success"]
    first_model = enroll_service._course_from_row(db.get_courses_by_status("")[0])
    courses = [first_model]
    enroll_service._reset_progress(courses)
    enroll_service._update_course_progress(
        first.id,
        increment_attempts=True,
        failures=7,
        message="保留历史",
    )
    assert cart_service.add_course(added)["success"]

    reconciled = enroll_service._reconcile_courses(courses)
    progress = {item["id"]: item for item in enroll_service.get_enroll_progress()["courses"]}

    assert [course.id for course in reconciled] == [added.id, first.id]
    assert progress[first.id]["attempts"] == 1
    assert progress[first.id]["failures"] == 7
    assert progress[added.id]["attempts"] == 0
    assert {row["status"] for row in db.get_active_courses()} == {database.STATUS_IN_PROGRESS}

    assert cart_service.update_course_preferences(first.id, auto_enabled=False)
    enroll_service._reconcile_courses(courses)
    progress_ids = {item["id"] for item in enroll_service.get_enroll_progress()["courses"]}
    first_row = next(row for row in db.get_courses_by_status("") if row["id"] == first.id)
    assert [course.id for course in courses] == [added.id]
    assert first.id not in progress_ids
    assert first_row["status"] == database.STATUS_NOT_STARTED


def test_retried_failure_reactivates_progress_without_losing_attempt_history(
    tmp_path,
    monkeypatch,
):
    db = DatabaseManager(str(tmp_path / "retry.db"))
    monkeypatch.setattr(cart_service, "db", db)
    failed = _course("failed")
    assert cart_service.add_course(failed)["success"]
    assert cart_service.update_status(failed.id, database.STATUS_FAILED)
    model = enroll_service._course_from_row(db.get_courses_by_status("")[0])
    enroll_service._reset_progress([model])
    enroll_service._update_course_progress(
        failed.id,
        status=database.STATUS_FAILED,
        increment_attempts=True,
        failures=1,
        message="曾经失败",
    )
    assert enroll_service.retry_cart_course(failed.id)["success"]

    queue: list[enroll_service.EnrollmentCourse] = []
    enroll_service._reconcile_courses(queue)
    progress = enroll_service.get_enroll_progress()["courses"][0]

    assert [course.id for course in queue] == [failed.id]
    assert progress["status"] == database.STATUS_IN_PROGRESS
    assert progress["attempts"] == 1
    assert progress["failures"] == 1
    assert "重新加入" in progress["message"]


def test_duplicate_add_cannot_reset_an_existing_course(tmp_path, monkeypatch):
    db = DatabaseManager(str(tmp_path / "duplicate.db"))
    monkeypatch.setattr(cart_service, "db", db)
    existing = _course("same")
    assert enroll_service.add_cart_course(existing)["success"]
    assert cart_service.update_status(existing.id, database.STATUS_SUCCESS)

    duplicate = enroll_service.add_cart_course(existing)

    assert duplicate["success"] is False
    assert duplicate["error_code"] == "COURSE_ALREADY_IN_CART"
    assert db.get_courses_by_status("")[0]["status"] == database.STATUS_SUCCESS


def test_bulk_priority_update_rolls_back_when_any_course_is_missing(tmp_path):
    db = DatabaseManager(str(tmp_path / "priority.db"))
    assert db.add_course(_course("first", rank=1, group="同组"))
    assert db.add_course(_course("second", rank=2, group="同组"))

    assert db.update_course_priorities([("first", 20), ("missing", 30)]) is False

    ranks = {row["id"]: row["priority_rank"] for row in db.get_courses_by_status("")}
    assert ranks == {"first": 0, "second": 1}


def test_new_courses_get_dense_ranks_within_their_group(tmp_path):
    db_path = tmp_path / "ranked.db"
    db = DatabaseManager(str(db_path))
    assert db.add_course(_course("first", rank=99, group="同组"))
    assert db.add_course(_course("second", rank=0, group="同组"))
    assert db.add_course(_course("other", rank=50, group="另一组"))

    rows = {row["id"]: row for row in db.get_courses_by_status("")}
    assert rows["first"]["priority_rank"] == 0
    assert rows["second"]["priority_rank"] == 1
    assert rows["other"]["priority_rank"] == 0

    db.close()
    reopened = DatabaseManager(str(db_path))
    reopened_rows = {row["id"]: row for row in reopened.get_courses_by_status("")}
    assert reopened_rows["first"]["priority_rank"] == 0
    assert reopened_rows["second"]["priority_rank"] == 1


def test_moving_course_to_another_group_appends_and_normalizes_ranks(tmp_path):
    db = DatabaseManager(str(tmp_path / "groups.db"))
    assert db.add_course(_course("a1", group="A"))
    assert db.add_course(_course("a2", group="A"))
    assert db.add_course(_course("b1", group="B"))

    assert db.update_course_preferences("a1", priority_group="B")

    rows = {row["id"]: row for row in db.get_courses_by_status("")}
    assert (rows["a2"]["priority_group"], rows["a2"]["priority_rank"]) == ("A", 0)
    assert (rows["b1"]["priority_group"], rows["b1"]["priority_rank"]) == ("B", 0)
    assert (rows["a1"]["priority_group"], rows["a1"]["priority_rank"]) == ("B", 1)
