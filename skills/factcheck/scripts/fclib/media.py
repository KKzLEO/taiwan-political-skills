"""Look up an outlet in data/<region>/media.toml by URL domain, id, name or alias."""

from __future__ import annotations

from urllib.parse import urlparse

from . import io


def load(region: str = "tw"):
    path = io.DATA_DIR / region / "media.toml"
    return io.read_toml(path).get("outlet", []) if path.exists() else []


def _host(query: str):
    if "://" not in query:
        return None
    return (urlparse(query).hostname or "").lower()


def lookup(query: str, outlets):
    q = query.strip()
    host = _host(q)
    if host:
        for o in outlets:
            for d in o.get("domains", []):
                d = d.lower()
                if host == d or host.endswith("." + d):
                    return o
        return None
    key = q.casefold()
    for o in outlets:
        names = [o.get("id", ""), o.get("name", "")] + list(o.get("aliases", []))
        if any(key == n.casefold() for n in names if n):
            return o
    return None
