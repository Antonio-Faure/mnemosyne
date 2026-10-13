"""Browser lease: one driver at a time, but a dead holder must not block it."""

from __future__ import annotations

import json
import os
import socket
import time

from mnemosyne.db import Database


def _db(tmp_path) -> Database:
    return Database(tmp_path / "lease.db")


def test_lease_is_exclusive(tmp_path):
    db = _db(tmp_path)
    assert db.try_lease("browser", ttl_s=60, owner="first") is True
    assert db.try_lease("browser", ttl_s=60, owner="second") is False
    db.release_lease("browser")
    assert db.try_lease("browser", ttl_s=60, owner="third") is True
    db.close()


def test_expired_lease_is_reclaimed(tmp_path):
    db = _db(tmp_path)
    db.try_lease("browser", ttl_s=0.01, owner="gone")
    time.sleep(0.05)
    assert db.try_lease("browser", ttl_s=60, owner="new") is True
    db.close()


def test_lease_of_a_dead_process_is_reclaimed_immediately(tmp_path):
    """A killed session must not hold the browser for the whole TTL."""
    db = _db(tmp_path)
    # a lease whose holder is a pid that cannot exist here
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?)",
        (
            "lease:browser",
            json.dumps(
                {
                    "owner": "cli",
                    "pid": 4_000_000,
                    "host": socket.gethostname(),
                    "expires": time.time() + 18_000,
                }
            ),
        ),
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is True
    db.close()


def test_lease_of_a_live_process_is_respected(tmp_path):
    db = _db(tmp_path)
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?)",
        (
            "lease:browser",
            json.dumps(
                {
                    "owner": "other",
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "expires": time.time() + 600,
                }
            ),
        ),
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is False
    db.close()


def test_legacy_float_lease_is_understood(tmp_path):
    """Leases written before the pid tracking were plain expiries."""
    db = _db(tmp_path)
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:browser', ?)",
        (str(time.time() + 600),),
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is False
    db._conn.execute(
        "UPDATE kv SET value = ? WHERE key = 'lease:browser'", (str(time.time() - 1),)
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is True
    db.close()


def test_lease_from_a_previous_incarnation_is_reclaimed(tmp_path):
    """In a container every heartbeat is pid 1: the start time tells them apart."""
    import json as _json

    from mnemosyne.db import _proc_start_time

    db = _db(tmp_path)
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:browser', ?)",
        (
            _json.dumps(
                {
                    "owner": "",
                    "pid": os.getpid(),  # same pid, previous generation
                    "host": socket.gethostname(),
                    "started": (_proc_start_time() or 0) - 10_000,
                    "expires": time.time() + 18_000,
                }
            ),
        ),
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is True
    db.close()


def test_lease_of_the_current_process_is_respected(tmp_path):
    import json as _json

    from mnemosyne.db import _proc_start_time

    db = _db(tmp_path)
    assert db.try_lease("browser", ttl_s=600, owner="me") is True
    row = db._conn.execute("SELECT value FROM kv WHERE key = 'lease:browser'").fetchone()
    held = _json.loads(row["value"])
    assert held["pid"] == os.getpid() and held["started"] == _proc_start_time()
    db.close()


def test_holder_from_a_previous_container_is_reclaimed(tmp_path):
    """Foreign namespace: liveness cannot be probed, only the renewed expiry.

    A live-looking lease from another hostname is NOT stolen (the host must not
    steal from the container, nor the container from the host); once its
    renewal stopped and the TTL lapsed, it is reclaimable.
    """
    import json as _json

    db = _db(tmp_path)
    held = {
        "owner": "",
        "pid": 1,
        "host": "an-old-container-id",
        "started": 12345,
        "instance": "deadbeef",
        "expires": time.time() + 300,
    }
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:browser', ?)", (_json.dumps(held),)
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is False

    held["expires"] = time.time() - 1
    db._conn.execute(
        "UPDATE kv SET value = ? WHERE key = 'lease:browser'", (_json.dumps(held),)
    )
    db._conn.commit()
    assert db.try_lease("browser", ttl_s=60, owner="next") is True
    db.close()


def test_renewal_extends_only_our_lease(tmp_path):
    db = _db(tmp_path)
    assert db.try_lease("browser", ttl_s=0.05, owner="me") is True
    assert db.renew_own_lease("browser", ttl_s=600) is True
    time.sleep(0.1)
    # the renewed lease is still alive for everyone else
    assert db.try_lease("browser", ttl_s=60, owner="other") is False
    db.close()


def test_release_and_renew_never_touch_a_foreign_lease(tmp_path):
    db = _db(tmp_path)
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:agency', ?)",
        (
            json.dumps(
                {
                    "owner": "host",
                    "pid": 1,
                    "host": "the-host",
                    "instance": "other",
                    "expires": time.time() + 300,
                }
            ),
        ),
    )
    db._conn.commit()
    assert db.renew_own_lease("agency", 600) is False
    assert db.release_own_lease("agency") is False
    assert db.lease_exists("agency") is True
    db.close()
