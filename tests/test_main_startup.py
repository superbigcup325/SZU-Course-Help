from __future__ import annotations

import sys
from types import SimpleNamespace

import main


def test_start_course_system_uses_terminal_card_key_prefill_without_new_prompt(monkeypatch, capsys):
    started = []
    prefilled = []
    fake_app = SimpleNamespace(
        get_login_url=lambda: "http://127.0.0.1:8000/login.html",
        configure_runtime_prefill=lambda student_id, card_key: prefilled.append(
            (student_id, card_key)
        ),
        start_server=lambda: started.append(True),
    )
    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: (_ for _ in ()).throw(AssertionError(f"unexpected prompt: {prompt}")),
    )

    main.start_course_system("2024110122", "SZU3.terminal")

    assert started == [True]
    assert prefilled == [("2024110122", "SZU3.terminal")]
    assert "请输入" not in capsys.readouterr().out
