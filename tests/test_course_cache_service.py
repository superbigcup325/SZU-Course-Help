from __future__ import annotations

import json

from services import course_cache_service


def _payload(*courses: dict) -> dict:
    return {
        "total_count": len(courses),
        "courses": list(courses),
        "msg": "",
        "is_error": False,
    }


def _scope(
    student_id: str = "2024110122",
    batch_code: str = "2026-1",
    campus_code: str = "01",
) -> course_cache_service.CatalogCacheScope:
    return course_cache_service.CatalogCacheScope(student_id, batch_code, campus_code)


def test_non_empty_page_is_scoped_and_does_not_persist_raw_student_id(tmp_path, monkeypatch):
    path = tmp_path / "courses.json"
    monkeypatch.setattr(course_cache_service, "_path", path)
    scope = _scope()
    payload = _payload({"course_name": "缓存课程"})

    assert course_cache_service.put_page(scope, "TJKC", 1, 10, payload) is True
    cached = course_cache_service.get_page(scope, "TJKC", 1, 10)

    assert cached is not None
    assert cached["courses"] == payload["courses"]
    assert cached["cached"] is True
    assert cached["has_cache"] is True
    assert cached["cache_read_only"] is True
    assert cached["cache_schema_version"] == course_cache_service.CACHE_SCHEMA_VERSION
    assert cached["cache_scope"] == {"batch_code": "2026-1", "campus_code": "01"}
    assert "2024110122" not in path.read_text(encoding="utf-8")


def test_account_batch_and_campus_scopes_never_cross(tmp_path, monkeypatch):
    monkeypatch.setattr(course_cache_service, "_path", tmp_path / "courses.json")
    original = _payload({"course_name": "仅当前范围"})
    assert course_cache_service.put_page(_scope(), "TJKC", 1, 10, original)

    assert course_cache_service.get_page(_scope("2024110999"), "TJKC", 1, 10) is None
    assert course_cache_service.get_page(_scope(batch_code="2026-2"), "TJKC", 1, 10) is None
    assert course_cache_service.get_page(_scope(campus_code="02"), "TJKC", 1, 10) is None


def test_empty_or_invalid_response_does_not_replace_existing_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(course_cache_service, "_path", tmp_path / "courses.json")
    scope = _scope()
    original = _payload({"course_name": "旧课程"})
    course_cache_service.put_page(scope, "TJKC", 1, 10, original)

    assert course_cache_service.put_page(scope, "TJKC", 1, 10, {"courses": []}) is False
    assert course_cache_service.put_page(scope, "TJKC", 1, 10, {"courses": "invalid"}) is False
    assert course_cache_service.get_page(scope, "TJKC", 1, 10)["courses"] == original["courses"]


def test_corrupt_or_wrong_schema_cache_is_treated_as_missing(tmp_path, monkeypatch):
    path = tmp_path / "courses.json"
    monkeypatch.setattr(course_cache_service, "_path", path)
    path.write_text("{not-json", encoding="utf-8")
    assert course_cache_service.get_page(_scope(), "TJKC", 1, 10) is None

    path.write_text(json.dumps({"schema": 1, "entries": {}}), encoding="utf-8")
    assert course_cache_service.get_page(_scope(), "TJKC", 1, 10) is None


def test_full_catalog_requires_completeness_and_supported_type(tmp_path, monkeypatch):
    monkeypatch.setattr(course_cache_service, "_path", tmp_path / "courses.json")
    scope = _scope()
    payload = _payload(
        {"course_name": "第一页课程"},
        {"course_name": "第二页课程"},
    )

    assert course_cache_service.put_full(scope, "TJKC", payload) is True
    cached = course_cache_service.get_full(scope, "TJKC")
    assert cached is not None
    assert cached["courses"] == payload["courses"]
    assert cached["full_catalog"] is True
    assert course_cache_service.put_full(scope, "FAWKC", payload) is False
    incomplete = {**payload, "total_count": 3}
    assert course_cache_service.put_full(scope, "FANKC", incomplete) is False


def test_latest_offline_catalog_is_still_isolated_by_account(tmp_path, monkeypatch):
    monkeypatch.setattr(course_cache_service, "_path", tmp_path / "courses.json")
    first_scope = _scope("2024110122", "old-batch", "01")
    other_scope = _scope("2024110999", "new-batch", "02")
    first = _payload({"course_name": "本人课程"})
    other = _payload({"course_name": "他人课程"})
    assert course_cache_service.put_full(first_scope, "FANKC", first)
    assert course_cache_service.put_full(other_scope, "FANKC", other)

    cached = course_cache_service.get_latest_full_for_student("2024110122", "FANKC")

    assert cached is not None
    assert cached["courses"] == first["courses"]
    assert cached["cache_scope"] == {"batch_code": "old-batch", "campus_code": "01"}
    assert course_cache_service.get_latest_full_for_student("2024110000", "FANKC") is None
