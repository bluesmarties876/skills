#!/usr/bin/env python3
"""
motion_client.py — shared HTTP layer for the Motion API (api.usemotion.com).

Auth
----
Every request carries the header ``X-API-Key: <your key>``. The key is read from
the ``MOTION_API_KEY`` environment variable, which the platform injects when the
script runs through RunWithCredentials. The key is never accepted as a command
line argument and is never printed or logged.

Conventions the API follows
---------------------------
* Base URL:            https://api.usemotion.com
* Paginated lists:     request ``cursor``, read ``meta.nextCursor``; the envelope
                       is ``{"meta": {"nextCursor": ..., "pageSize": ...}, "<collection>": [...]}``
* Non-paginated lists: a bare JSON array
* Errors:              non-2xx with a JSON body ``{"message", "error", "statusCode"}``
* Rate limits:         12 requests/minute (individual), up to 120 (teams)

This module also exposes a tiny client-side rate limiter, because bulk work over
a 12/minute budget will otherwise burn through the retry budget needlessly.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://api.usemotion.com"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 5
# The default "Python-urllib/x.y" User-Agent is blocked at the edge with a 403
# (Cloudflare error 1010, browser_signature_banned) before the request ever
# reaches the API. Always identify explicitly.
USER_AGENT = "motion-api-skill/1.0 (+https://docs.usemotion.com)"
# 429 is the rate limit; 5xx are worth retrying. Everything else is surfaced at once.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class MotionError(Exception):
    """Any failed call: non-2xx response, transport failure, or bad configuration."""

    def __init__(self, message, status=None, payload=None, method=None, url=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload
        self.method = method
        self.url = url

    def as_dict(self):
        return {
            "error": self.message,
            "status": self.status,
            "method": self.method,
            "url": self.url,
            "payload": self.payload,
        }


def _default_transport(method, url, headers, body, timeout):
    """One HTTP round trip. Returns (status, headers, text) and never raises on 4xx/5xx."""
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        return exc.code, dict(exc.headers or {}), raw
    except urllib.error.URLError as exc:
        raise MotionError(f"Could not reach {url}: {exc.reason}", method=method, url=url)


class RateLimiter:
    """Space calls out so a bulk run respects the account's requests-per-minute budget."""

    def __init__(self, requests_per_minute=None):
        self.min_interval = (60.0 / requests_per_minute) if requests_per_minute else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        if not self.min_interval:
            return
        with self._lock:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            self._last = time.monotonic()


class MotionClient:
    def __init__(
        self,
        api_key=None,
        base_url=BASE_URL,
        timeout=DEFAULT_TIMEOUT,
        max_retries=MAX_RETRIES,
        requests_per_minute=None,
        transport=None,
        sleeper=time.sleep,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("MOTION_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport or _default_transport
        self.limiter = RateLimiter(requests_per_minute)
        self._sleep = sleeper
        self.last_request_url = None

    # -- request plumbing ---------------------------------------------------

    def _headers(self):
        if not self.api_key:
            raise MotionError(
                "MOTION_API_KEY is not set. The credential is injected automatically when "
                "this script runs with its skill credentials; there is no way to pass a key "
                "on the command line."
            )
        return {"X-API-Key": self.api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT}

    def _url(self, path, params=None):
        if not path.startswith("/"):
            path = "/" + path
        url = self.base_url + path
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != [] and v != ""}
        if clean:
            # doseq=True so array params (status, ids) serialize as repeated keys.
            url += "?" + urllib.parse.urlencode(clean, doseq=True)
        return url

    @staticmethod
    def _parse(raw):
        if raw is None or raw == "":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def request(self, method, path, params=None, body=None, retries=None):
        """Perform one call and return the parsed JSON body (or None for empty responses)."""
        method = method.upper()
        url = self._url(path, params)
        self.last_request_url = url
        attempts = self.max_retries if retries is None else retries
        attempt = 0

        while True:
            self.limiter.wait()
            try:
                status, headers, raw = self.transport(method, url, self._headers(), body, self.timeout)
            except MotionError:
                raise
            except Exception as exc:  # transport-level surprise
                raise MotionError(f"{method} {url} failed: {exc}", method=method, url=url)

            if 200 <= status < 300:
                return self._parse(raw)

            payload = self._parse(raw)
            detail = payload.get("message") if isinstance(payload, dict) else raw
            # Validation failures carry a per-field breakdown under "errors"; without it
            # the top-level "Validation failed" tells the caller nothing actionable.
            if isinstance(payload, dict) and payload.get("errors"):
                reasons = [
                    e.get("message") for e in payload["errors"]
                    if isinstance(e, dict) and e.get("message")
                ]
                if reasons:
                    detail = f"{detail} — " + "; ".join(reasons)
            message = f"{method} {url} -> HTTP {status}: {detail}"

            if status in RETRYABLE_STATUS and attempt < attempts:
                attempt += 1
                self._sleep(self._backoff_seconds(attempt, headers, status))
                continue

            raise MotionError(message, status=status, payload=payload, method=method, url=url)

    @staticmethod
    def _backoff_seconds(attempt, headers, status):
        """Honour Retry-After when the server sends it; otherwise back off exponentially."""
        raw = None
        for key in ("Retry-After", "retry-after"):
            if headers and key in headers:
                raw = headers[key]
                break
        if raw:
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                pass
        return min(2 ** attempt, 32) if status == 429 else min(2 ** (attempt - 1), 8)

    # -- convenience --------------------------------------------------------

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body=None, params=None):
        return self.request("POST", path, params=params, body=body)

    def patch(self, path, body=None, params=None):
        return self.request("PATCH", path, params=params, body=body)

    def delete(self, path, params=None):
        return self.request("DELETE", path, params=params)

    def paginate(self, path, params=None, collection_key=None, max_pages=100):
        """Follow meta.nextCursor until exhausted; return the concatenated collection.

        ``collection_key`` names the array inside the envelope (``tasks``, ``projects``,
        ``users``, ``workspaces``, ``comments``). If the endpoint returns a bare array
        instead, the array is returned as-is and max_pages is irrelevant.
        """
        items = []
        cursor = None
        base_params = dict(params or {})

        for _ in range(max_pages):
            page_params = dict(base_params)
            if cursor:
                page_params["cursor"] = cursor
            page = self.get(path, params=page_params)

            if isinstance(page, list):
                items.extend(page)
                return items

            if not isinstance(page, dict):
                # Neither an envelope nor a bare array: the response was truncated,
                # wrapped by a gateway, or otherwise not what this endpoint returns.
                # Returning what we have so far would hand back a partial answer that
                # looks complete, which is the worst failure direction for a caller
                # who asked for everything. Refuse instead.
                raise MotionError(
                    f"Pagination for {path} got a page that is neither a JSON object nor an "
                    f"array ({type(page).__name__}); refusing to return a partial result."
                )

            key = collection_key
            if key is None:
                key = next((k for k, v in page.items() if isinstance(v, list) and k != "meta"), None)
            if key and isinstance(page.get(key), list):
                items.extend(page[key])

            cursor = (page.get("meta") or {}).get("nextCursor")
            if not cursor:
                return items

        raise MotionError(
            f"Pagination did not finish within {max_pages} pages for {path}; "
            "narrow the query rather than looping further."
        )


def emit(data):
    """Print a result as JSON — the shape every caller of these scripts should consume."""
    json.dump(data, sys.stdout, indent=2, sort_keys=False, default=str)
    sys.stdout.write("\n")


def fail(exc):
    """Print a MotionError as JSON on stderr and exit non-zero."""
    if isinstance(exc, MotionError):
        json.dump(exc.as_dict(), sys.stderr, indent=2, default=str)
    else:
        json.dump({"error": str(exc)}, sys.stderr, indent=2)
    sys.stderr.write("\n")
    sys.exit(1)
