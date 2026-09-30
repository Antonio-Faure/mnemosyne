from datetime import datetime

from mnemosyne.journal import Control, Journal


def test_journal_append_and_read(tmp_path):
    journal = Journal(tmp_path / "journal")
    journal.append("hello world", source="test")
    text = journal.read()
    assert "hello world" in text
    assert datetime.now().date().isoformat() in text


def test_control_inbox_consume_once(tmp_path):
    control = Control(tmp_path / "control")
    control.post("first")
    control.post("second")
    assert control.pending() == ["first", "second"]
    assert control.consume() == ["first", "second"]
    assert control.consume() == []


def test_control_directives_ignore_comments(tmp_path):
    control = Control(tmp_path / "control")
    assert control.directives() == ""
    control.directives_path.write_text(
        "# Directives\n<!-- note -->\nPriorise Lacq.\nÉvite les cartes.\n", encoding="utf-8"
    )
    assert control.directives() == "Priorise Lacq.\nÉvite les cartes."
