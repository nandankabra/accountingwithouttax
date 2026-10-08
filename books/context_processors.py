"""Version local assets so a corrected client is loaded after a release."""
from functools import lru_cache
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parent/'static/books'


@lru_cache(maxsize=1)
def digest(js_modified,css_modified):
    return hashlib.sha256((ROOT/'app.js').read_bytes()+(ROOT/'app.css').read_bytes()).hexdigest()[:16]


def assets(request):
    return {'asset_version':digest((ROOT/'app.js').stat().st_mtime_ns,(ROOT/'app.css').stat().st_mtime_ns)}
