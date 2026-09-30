import re
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


def test_service_journal_has_title_and_dated_entries(tmp_path):
    journal = Journal(tmp_path / "journal")
    journal.append_service("acme", "demande d'accès envoyée", title="Acme Archives")
    journal.append_service("acme", "clé API obtenue")

    assert journal.list_services() == ["acme"]
    text = journal.read_service("acme")
    assert "# Journal de service — Acme Archives" in text
    assert "demande d'accès envoyée" in text
    # every entry carries a full date + time
    assert re.search(r"- \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[info\]", text)


def test_daily_journal_entries_are_dated(tmp_path):
    journal = Journal(tmp_path / "journal")
    journal.append("hello", source="test")
    assert re.search(r"- \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[info\] test: hello", journal.read())


def test_control_directives_ignore_comments(tmp_path):
    control = Control(tmp_path / "control")
    assert control.directives() == ""
    control.directives_path.write_text(
        "# Directives\n<!-- note -->\nPriorise Lacq.\nÉvite les cartes.\n", encoding="utf-8"
    )
    assert control.directives() == "Priorise Lacq.\nÉvite les cartes."
