import sqlite3

from mnemosyne.browser.history import read_history


def _make_history(path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER,"
        " last_visit_time INTEGER)"
    )
    con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
    rows = [
        ("https://mail.google.com/mail/u/0/#inbox", 3, 13300000000000000),
        ("https://www.ina.fr/", 2, 13300000010000000),
        ("https://gallica.bnf.fr/", 1, 13300000020000000),
    ]
    con.executemany("INSERT INTO urls (url, visit_count, last_visit_time) VALUES (?,?,?)", rows)
    con.executemany(
        "INSERT INTO visits (url, visit_time) VALUES (?,?)",
        [("https://mail.google.com/", 1), ("https://www.ina.fr/", 1)],
    )
    con.commit()
    con.close()


def test_read_history_missing_file(tmp_path):
    report = read_history(tmp_path / "nope")
    assert report["exists"] is False


def test_read_history_counts_and_probes(tmp_path):
    path = tmp_path / "History"
    _make_history(path)
    report = read_history(path)
    assert report["exists"] is True
    assert report["urls"] == 3
    assert report["visits"] == 2
    assert report["probes"]["mail.google.com"] == 1
    assert report["probes"]["ina.fr"] == 1
    assert report["probes"]["archive.org"] == 0
    assert report["first_seen"] is not None
