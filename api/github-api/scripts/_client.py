"""Shared GitHub REST client. Reads GITHUB_PAT from env.

Stdlib-only (urllib) — no `requests` dependency. The sandbox does NOT have
`requests` pre-installed; vendoring on urllib keeps every script in this skill
self-contained on first call.

Exposes a small Response shim with the attributes the rest of the skill reads:
  .status_code, .headers, .text, .content, .json()
"""
import io
import json as _json
import os
import sys
import time
from urllib import request as _urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

API = "https://api.github.com"


class Response:
    """Minimal response wrapper exposing the attributes the scripts read."""

    def __init__(self, status_code, headers, body_bytes):
        self.status_code = status_code
        # Header lookup is case-insensitive on real HTTP; emulate with a dict
        # whose keys are the original casing but with .get() that falls back.
        self.headers = {k: v for k, v in headers.items()}
        self.content = body_bytes
        try:
            self.text = body_bytes.decode("utf-8", errors="replace")
        except Exception:
            self.text = ""

    def json(self):
        if not self.content:
            return None
        return _json.loads(self.content.decode("utf-8"))


def token():
    t = os.environ.get("GITHUB_PAT")
    if not t:
        sys.stderr.write(
            "ERROR: GITHUB_PAT not set in env. This skill's scripts must be run via "
            "RunWithCredentials(skillName='github-api', command='python3 ...') "
            "— bare `python3` calls do NOT have GITHUB_PAT injected.\n"
        )
        sys.exit(2)
    return t


def headers(extra=None):
    h = {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hyperagent-github-skill/1.0",
    }
    if extra:
        h.update(extra)
    return h


def _build_url(path, params):
    url = path if path.startswith("http") else API + path
    if params:
        # Drop None values so callers can pass optional params.
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            sep = "&" if "?" in url else "?"
            url = url + sep + urlencode(clean)
    return url


def _do_request(method, url, hdrs, body_bytes, timeout):
    req = _urlreq.Request(url, data=body_bytes, method=method)
    for k, v in hdrs.items():
        req.add_header(k, v)
    try:
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            return Response(resp.getcode(), dict(resp.headers.items()), resp.read())
    except HTTPError as e:
        # HTTPError is a Response-like object — extract status/body so callers
        # can inspect rate-limit headers etc.
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return Response(e.code, dict(e.headers.items()) if e.headers else {}, body)


def request(method, path, *, params=None, data=None, json_body=None, accept=None, stream=False, retries=3):
    """Mirror of the old requests-backed signature.

    `stream` is accepted for compatibility but ignored — urllib reads the full
    response. None of the skill's current scripts rely on streaming.
    """
    url = _build_url(path, params)
    extra = {"Accept": accept} if accept else None
    hdrs = headers(extra)

    body_bytes = None
    if json_body is not None:
        body_bytes = _json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif data is not None:
        if isinstance(data, (bytes, bytearray)):
            body_bytes = bytes(data)
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
        else:
            # Form-encode dicts/lists, matching requests' behaviour on data=.
            body_bytes = urlencode(data).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")

    last_exc = None
    for attempt in range(retries):
        try:
            r = _do_request(method, url, hdrs, body_bytes, timeout=60)
        except URLError as e:
            last_exc = e
            time.sleep(1 + attempt * 2)
            continue

        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = int(r.headers.get("X-RateLimit-Reset", "0") or "0")
            wait = max(5, reset - int(time.time()))
            sys.stderr.write(f"Rate limited; sleeping {wait}s\n")
            time.sleep(min(wait, 90))
            continue
        if r.status_code >= 500 and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        return r

    if last_exc:
        raise last_exc
    return r


def paginate(path, params=None, max_pages=50):
    """Yield items across paginated endpoints. Works for endpoints returning a list."""
    page = 1
    params = dict(params or {})
    params.setdefault("per_page", 100)
    while page <= max_pages:
        params["page"] = page
        r = request("GET", path, params=params)
        if r.status_code != 200:
            sys.stderr.write(f"Pagination failed: {r.status_code} {r.text[:200]}\n")
            return
        items = r.json()
        if not isinstance(items, list) or not items:
            return
        for it in items:
            yield it
        if len(items) < params["per_page"]:
            return
        page += 1


def die(r, ctx=""):
    sys.stderr.write(f"FAILED ({ctx}) {r.status_code}: {r.text[:500]}\n")
    sys.exit(1)


def ok(r, expected=(200, 201, 204)):
    return r.status_code in expected
