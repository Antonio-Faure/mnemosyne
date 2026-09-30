from mnemosyne.util import atomic_write_text, cleanup_orphan_tmp, parse_year, stable_id


def test_parse_year():
    assert parse_year("circa 1890") == 1890
    assert parse_year("1950-1960") == 1950
    assert parse_year("no year here") is None
    assert parse_year(None) is None


def test_stable_id_deterministic():
    assert stable_id("a", 1) == stable_id("a", 1)
    assert stable_id("a", 1) != stable_id("a", 2)


def test_atomic_write_leaves_no_tmp(tmp_path):
    target = tmp_path / "out.json"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    assert list(tmp_path.glob("*.tmp")) == []


def test_cleanup_orphan_tmp(tmp_path):
    (tmp_path / "a.tmp").write_text("x")
    assert cleanup_orphan_tmp(tmp_path) == 1
    assert not (tmp_path / "a.tmp").exists()
