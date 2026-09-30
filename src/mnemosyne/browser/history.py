"""Read the dedicated Chrome profile's history (warmup growth monitoring).

Chrome keeps history in a locked SQLite `History` file; we copy it to a temp
path before querying so we never disturb the running browser.
"""

from __future__ import annotations

import collections
import shutil
import sqlite3
import tempfile
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

#: Chrome timestamps are microseconds since 1601-01-01 (UTC).
_EPOCH = datetime(1601, 1, 1)

DEFAULT_PROBES = [
    "mail.google.com",
    "accounts.google.com",
    "fr.wikipedia.org",
    "gallica.bnf.fr",
    "ina.fr",
    "commons.wikimedia.org",
    "europeana.eu",
    "archive.org",
]


def _to_dt(webkit_us: int | None) -> datetime | None:
    if not webkit_us:
        return None
    try:
        return _EPOCH + timedelta(microseconds=int(webkit_us))
    except (ValueError, OverflowError):
        return None


def read_history(
    path: str | Path, *, top: int = 15, probes: list[str] | None = None
) -> dict:
    path = Path(path)
    if not path.exists():
        return {"exists": False, "path": str(path)}

    with tempfile.NamedTemporaryFile(prefix="mnemo-history-", suffix=".db", delete=False) as fh:
        tmp = fh.name
    shutil.copy2(path, tmp)
    try:
        con = sqlite3.connect(tmp)
        try:
            total = con.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
            try:
                visits = con.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
            except sqlite3.Error:
                visits = 0
            rows = con.execute(
                "SELECT url, visit_count, last_visit_time FROM urls"
            ).fetchall()
        finally:
            con.close()
    finally:
        Path(tmp).unlink(missing_ok=True)

    domains: collections.Counter[str] = collections.Counter()
    times: list[datetime] = []
    for url, _vc, last in rows:
        host = urllib.parse.urlparse(url).netloc
        domains[host] += 1
        dt = _to_dt(last)
        if dt:
            times.append(dt)

    probe_list = probes or DEFAULT_PROBES
    return {
        "exists": True,
        "path": str(path),
        "urls": total,
        "visits": visits,
        "domains_count": len(domains),
        "top_domains": domains.most_common(top),
        "probes": {p: sum(v for k, v in domains.items() if p in k) for p in probe_list},
        "first_seen": min(times).isoformat(sep=" ") if times else None,
        "last_seen": max(times).isoformat(sep=" ") if times else None,
    }
