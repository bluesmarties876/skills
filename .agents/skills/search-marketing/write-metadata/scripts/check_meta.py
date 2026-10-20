#!/usr/bin/env python3
"""Read a page's search metadata and check candidate titles and descriptions.

Subcommands:
  fetch SOURCE   SOURCE is an http(s) URL, a local HTML file, or - for stdin.
  check FILE     FILE is a JSON candidates file, or - for stdin.
  --selftest     prove every check fires on a planted case and stays quiet on a clean one.

Python 3.9+, standard library only. `fetch` with a URL is the only network call.
No credentials are read.

Exit codes: 0 result printed; 1 selftest failed; 2 bad usage or input;
3 internal error; 4 the URL could not be fetched.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 20
USER_AGENT = "write-metadata-check/1.0 (+metadata review)"

TITLE_MIN = 40
TITLE_SOFT_MAX = 60
TITLE_HARD_MAX = 70
DESC_MIN = 120
DESC_SOFT_MAX = 160
KEY_INFO_CHARS = 100
H1_MATCH_MIN = 0.5
REPEAT_TITLE_MIN = 0.8

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in",
    "is", "it", "of", "on", "or", "the", "to", "with", "your", "you", "our", "we",
    "what", "why", "who", "this", "that", "vs",
}


class InputError(Exception):
    pass


class FetchError(Exception):
    pass


# ---------- fetch ----------

class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self.h1s: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.lang = ""
        self._in_title = False
        self._in_svg = 0
        self._h1_depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "svg":
            self._in_svg += 1
        elif tag == "html" and not self.lang:
            self.lang = a.get("lang", "").strip()
        elif tag == "title" and not self._in_svg:
            self._in_title = True
            self._buf = []
        elif tag == "h1":
            if self._h1_depth == 0:
                self._buf = []
            self._h1_depth += 1
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").strip().lower()
            if key:
                self.meta.setdefault(key, []).append(a.get("content", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg" and self._in_svg:
            self._in_svg -= 1
        elif tag == "title" and self._in_title:
            self._in_title = False
            self.titles.append(_clean("".join(self._buf)))
        elif tag == "h1" and self._h1_depth:
            self._h1_depth -= 1
            if self._h1_depth == 0:
                self.h1s.append(_clean("".join(self._buf)))

    def handle_data(self, data: str) -> None:
        if self._in_title or self._h1_depth:
            self._buf.append(data)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _decode(raw: bytes, header_charset: str | None) -> str:
    charset = header_charset
    if not charset:
        m = re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_\-]+)", raw[:4096], re.I)
        if m:
            charset = m.group(1).decode("ascii", "replace")
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _read_source(source: str) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                ctype = resp.headers.get_content_type()
                if ctype not in ("text/html", "application/xhtml+xml"):
                    raise FetchError(f"not an HTML page: content type is {ctype}")
                raw = resp.read(MAX_BYTES + 1)
                final_url = resp.geturl()
                charset = resp.headers.get_content_charset()
        except urllib.error.HTTPError as e:
            raise FetchError(f"HTTP {e.code} from {source}")
        except (urllib.error.URLError, OSError) as e:
            raise FetchError(f"could not reach {source}: {getattr(e, 'reason', e)}")
        if final_url != source:
            warnings.append(f"redirected to {final_url}")
    else:
        try:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1) if source == "-" else open(source, "rb").read(MAX_BYTES + 1)
        except OSError as e:
            raise InputError(f"cannot read {source}: {e.strerror}")
        final_url, charset = source, None
    if len(raw) > MAX_BYTES:
        raw = raw[:MAX_BYTES]
        warnings.append("page larger than 5 MB; only the first 5 MB was read")
    return _decode(raw, charset), final_url, warnings


def parse_page(html: str) -> dict[str, Any]:
    p = _MetaParser()
    p.feed(html)
    p.close()

    def first(key: str) -> str:
        vals = p.meta.get(key, [])
        return _clean(vals[0]) if vals else ""

    warnings: list[str] = []
    if len(p.titles) > 1:
        warnings.append(f"{len(p.titles)} title elements; the first is reported")
    if not p.h1s:
        warnings.append("no h1 element")
    elif len(p.h1s) > 1:
        warnings.append(f"{len(p.h1s)} h1 elements; Google may not know which is the main title")
    if len(p.meta.get("description", [])) > 1:
        warnings.append("more than one meta description; the first is reported")
    robots = " ".join(p.meta.get("robots", []) + p.meta.get("googlebot", [])).lower()
    if "noindex" in robots:
        warnings.append("robots noindex: the page is excluded from search, so its metadata will not show")
    if "nosnippet" in robots:
        warnings.append("robots nosnippet: Google will show no description for this page")
    if not p.titles and not p.h1s:
        warnings.append("no title and no h1 in the raw HTML; the page may render in the browser, so supply the rendered HTML as a file")
    return {
        "title": p.titles[0] if p.titles else "",
        "description": first("description"),
        "h1": p.h1s,
        "og_title": first("og:title"),
        "og_description": first("og:description"),
        "og_site_name": first("og:site_name"),
        "lang": p.lang,
        "robots": robots,
        "warnings": warnings,
    }


def cmd_fetch(source: str) -> dict[str, Any]:
    html, final_url, warnings = _read_source(source)
    page = parse_page(html)
    page["warnings"] = warnings + page["warnings"]
    return {"source": final_url, **page}


# ---------- check ----------

def _singular(w: str) -> str:
    if len(w) <= 3 or w.endswith(("ss", "us", "is")):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "sses", "xes", "zes")):
        return w[:-2]
    if w.endswith("s"):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_singular(w) for w in re.findall(r"[^\W_]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def _script(text: str) -> str:
    counts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            key = name.split(" ")[0] if name else "UNKNOWN"
            if key == "CJK" or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name:
                key = "CJK"
            counts[key] = counts.get(key, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def _repeats(words: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for w in words:
        if len(w) >= 3:
            out[w] = out.get(w, 0) + 1
    return {w: n for w, n in out.items() if n >= 2}


def _brand_count(text: str, brand: str) -> int:
    return len(re.findall(r"(?<!\w)" + re.escape(brand.lower()) + r"(?!\w)", text.lower())) if brand else 0


def check_candidate(c: dict[str, str], page: dict[str, Any], brand: str, query: str) -> dict[str, Any]:
    title = _clean(c["title"])
    desc = _clean(c["description"])
    issues: list[dict[str, str]] = []

    def add(level: str, code: str, detail: str) -> None:
        issues.append({"level": level, "code": code, "detail": detail})

    tl, dl = len(title), len(desc)
    brand_words = set(_words(brand))

    if not title:
        add("fail", "title-empty", "no title text")
    elif tl > TITLE_HARD_MAX:
        add("fail", "title-over-70", f"{tl} characters; titles over 70 were almost always rewritten")
    elif tl > TITLE_SOFT_MAX:
        add("warn", "title-over-60", f"{tl} characters; likely to be truncated")
    elif tl < TITLE_MIN:
        add("warn", "title-under-40", f"{tl} characters; short titles are rewritten more often")

    h1s = page.get("h1") or []
    if title and not h1s:
        add("warn", "no-h1-to-match", "the page has no h1, so title-to-h1 agreement cannot be checked")
    elif title:
        h1w = set(_words(h1s[0])) - brand_words
        tw = set(_words(title)) - brand_words
        if not h1w:
            add("warn", "no-h1-to-match", "the h1 has no words to compare once common words and the brand are set aside")
        else:
            share = len(h1w & tw) / len(h1w)
            if share < H1_MATCH_MIN:
                add("warn", "title-h1-mismatch", f"shares {share:.0%} of the h1's words; titles that match the h1 are rewritten far less")

    trep = _repeats([w for w in _words(title) if w not in brand_words])
    if any(n >= 3 for n in trep.values()):
        add("fail", "title-stuffing", "repeated: " + ", ".join(sorted(trep)))
    elif trep:
        add("warn", "title-repeated-word", "repeated: " + ", ".join(sorted(trep)))

    if brand and _brand_count(title, brand) > 1:
        add("warn", "brand-repeated", f"'{brand}' appears {_brand_count(title, brand)} times in the title")

    if query:
        qw = set(_words(query))
        if not qw:
            add("warn", "query-no-words", "the query is only common words, so query placement was not checked")
        if qw and not qw <= set(_words(title)):
            add("warn", "query-missing-from-title", "missing: " + ", ".join(sorted(qw - set(_words(title)))))
        if qw and desc and not qw <= set(_words(desc[:KEY_INFO_CHARS])):
            add("warn", "query-not-in-first-100", "the query's words are not all in the description's first 100 characters")

    if not desc:
        add("fail", "description-empty", "no description text")
    elif dl > DESC_SOFT_MAX:
        add("warn", "description-over-160", f"{dl} characters; likely to be truncated")
    elif dl < DESC_MIN:
        add("warn", "description-under-120", f"{dl} characters; may be too thin to describe the page")

    if title and desc:
        first_sentence = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0]
        fw, tw = set(_words(first_sentence)), set(_words(title))
        if fw and len(fw & tw) / len(fw) >= REPEAT_TITLE_MIN:
            add("warn", "description-repeats-title", "the first sentence mostly repeats the title; add detail the title does not give")

    drep = _repeats(_words(desc))
    if any(n >= 3 for n in drep.values()):
        add("warn", "description-stuffing", "repeated 3+ times: " + ", ".join(sorted(w for w, n in drep.items() if n >= 3)))

    page_text = (h1s[0] if h1s else "") or page.get("title", "")
    ps = _script(page_text)
    for field, text in (("title", title), ("description", desc)):
        cs = _script(text)
        if ps and cs and cs != ps:
            add("warn", f"{field}-script-mismatch", f"written in {cs} script but the page is {ps}; Google may replace it")

    levels = {i["level"] for i in issues}
    verdict = "FAIL" if "fail" in levels else "WARN" if "warn" in levels else "OK"
    return {"title": title, "title_chars": tl, "description": desc, "description_chars": dl,
            "verdict": verdict, "issues": issues}


def validate(data: Any) -> tuple[dict[str, Any], str, str, list[dict[str, str]]]:
    if not isinstance(data, dict):
        raise InputError("the input must be a JSON object with page and candidates")
    page = data.get("page")
    if not isinstance(page, dict):
        raise InputError("page must be an object; paste the output of fetch")
    h1 = page.get("h1", [])
    if isinstance(h1, str):
        h1 = [h1]
    if not isinstance(h1, list) or not all(isinstance(x, str) for x in h1):
        raise InputError("page.h1 must be a list of strings")
    page = {**page, "h1": [x for x in h1 if x.strip()]}
    for key in ("brand", "query"):
        if key in data and not isinstance(data[key], str):
            raise InputError(f"{key} must be a string")
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        raise InputError("candidates must list at least one {title, description}")
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            raise InputError(f"candidates[{i}] must be an object")
        for f in ("title", "description"):
            if not isinstance(c.get(f), str):
                raise InputError(f"candidates[{i}].{f} must be a string")
    return page, data.get("brand", "").strip(), data.get("query", "").strip(), cands


def cmd_check(data: Any) -> dict[str, Any]:
    page, brand, query, cands = validate(data)
    results = []
    seen: dict[tuple[str, str], int] = {}
    for i, c in enumerate(cands):
        r = check_candidate(c, page, brand, query)
        key = (r["title"].lower(), r["description"].lower())
        if key in seen:
            r["issues"].append({"level": "warn", "code": "duplicate-candidate",
                                "detail": f"same as candidate {seen[key]}"})
            if r["verdict"] == "OK":
                r["verdict"] = "WARN"
        else:
            seen[key] = i
        results.append({"candidate": i, **r})
    return {"brand": brand, "query": query, "h1": page["h1"][0] if page["h1"] else "",
            "candidates": results}


# ---------- selftest ----------

def selftest() -> int:
    failing = 0

    def expect(name: str, cond: bool) -> None:
        nonlocal failing
        print(("ok    " if cond else "FAIL  ") + name)
        if not cond:
            failing += 1

    html = ("<html lang='en'><head><title>Old</title><meta name='description' content='Old desc'>"
            "<meta property='og:title' content='OG'><svg><title>icon</title></svg></head>"
            "<body><h1>Expense tracking <b>for small teams</b></h1></body></html>")
    pg = parse_page(html)
    expect("fetch reads title", pg["title"] == "Old")
    expect("fetch ignores svg title", len(pg["h1"]) == 1 and "icon" not in pg["title"])
    expect("fetch reads nested h1", pg["h1"] == ["Expense tracking for small teams"])
    expect("fetch reads description and og", pg["description"] == "Old desc" and pg["og_title"] == "OG")
    expect("fetch reads lang", pg["lang"] == "en")
    expect("fetch warns no h1", "no h1 element" in parse_page("<title>x</title>")["warnings"])
    expect("fetch warns nosnippet", any("nosnippet" in w for w in parse_page(
        "<title>x</title><h1>x</h1><meta name='robots' content='nosnippet'>")["warnings"]))
    expect("fetch warns client-rendered", any("rendered" in w for w in parse_page("<div id=app></div>")["warnings"]))

    page = {"h1": ["Expense tracking for small teams"], "title": "Old"}
    good = {"title": "Expense Tracking for Small Teams, Set Up in a Day | Ledgerly",
            "description": "Simple expense tracking for teams of 5 to 50: snap receipts, approve claims on your phone, sync to your accounts. Free 14-day trial, no card needed."}

    def codes(cand: dict[str, str], brand: str = "Ledgerly", query: str = "expense tracking") -> set[str]:
        return {i["code"] for i in check_candidate(cand, page, brand, query)["issues"]}

    r = check_candidate(good, page, "Ledgerly", "expense tracking")
    expect("clean candidate is OK", r["verdict"] == "OK")
    expect("title-empty", "title-empty" in codes({**good, "title": " "}))
    expect("title-over-70", "title-over-70" in codes({**good, "title": "x" * 71}))
    expect("title-over-60", "title-over-60" in codes({**good, "title": "Expense Tracking for Small Teams and Growing Firms | Ledgerly"}))
    expect("title-under-40", "title-under-40" in codes({**good, "title": "Expense Tracking | Ledgerly"}))
    expect("title-h1-mismatch", "title-h1-mismatch" in codes({**good, "title": "Receipts Made Painless Across Every Device | Ledgerly"}))
    expect("no-h1-to-match", "no-h1-to-match" in {i["code"] for i in check_candidate(good, {"h1": []}, "", "")["issues"]})
    expect("no-h1-to-match on a stopword h1", "no-h1-to-match" in {i["code"] for i in check_candidate(good, {"h1": ["How to"]}, "", "")["issues"]})
    expect("plurals match singulars", "query-missing-from-title" not in codes({**good, "title": "Expense Tracking for Small Teams, Set Up in a Day | Ledgerly"}, query="small team expenses")
           and _words("coaches stories teams class") == ["coach", "story", "team", "class"])
    expect("query-no-words", "query-no-words" in codes(good, query="how to"))
    expect("title-repeated-word", "title-repeated-word" in codes({**good, "title": "Expense Tracking and Expense Reports for Small Teams"}))
    expect("title-stuffing", "title-stuffing" in codes({**good, "title": "Expense app, expense tool, expense tracking, small teams"}))
    expect("brand-repeated", "brand-repeated" in codes({**good, "title": "Ledgerly Expense Tracking for Small Teams | Ledgerly"}))
    expect("brand not counted as repeat", "title-repeated-word" not in codes({**good, "title": "Ledgerly Expense Tracking for Small Teams | Ledgerly"}))
    expect("query-missing-from-title", "query-missing-from-title" in codes(good, query="receipt scanner"))
    expect("query-not-in-first-100", "query-not-in-first-100" in codes(good, query="free trial"))
    expect("description-empty", "description-empty" in codes({**good, "description": ""}))
    expect("description-over-160", "description-over-160" in codes({**good, "description": good["description"] + " Loved by finance leads everywhere."}))
    expect("description-under-120", "description-under-120" in codes({**good, "description": "Expense tracking for teams."}))
    expect("description-repeats-title", "description-repeats-title" in codes({**good, "description": "Expense tracking for small teams. " + good["description"]}))
    expect("description-stuffing", "description-stuffing" in codes({**good, "description": "Expense app with expense tools for expense claims and more " * 2}))
    expect("title-script-mismatch", "title-script-mismatch" in codes({**good, "title": "Учёт расходов для небольших команд и компаний"}))
    out = cmd_check({"page": page, "candidates": [good, good]})
    expect("duplicate-candidate", any(i["code"] == "duplicate-candidate" for i in out["candidates"][1]["issues"]))
    for bad, name in (([], "non-object input"), ({"page": page, "candidates": []}, "empty candidates"),
                      ({"page": page, "candidates": [{"title": "x"}]}, "missing description"),
                      ({"candidates": [good]}, "missing page")):
        try:
            cmd_check(bad)
            expect("rejects " + name, False)
        except InputError:
            expect("rejects " + name, True)

    print(f"{'PASS' if failing == 0 else 'FAIL'}: {failing} failing")
    return 0 if failing == 0 else 1


# ---------- main ----------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="check_meta.py", description="Read a page's search metadata and check candidates.")
    parser.add_argument("--selftest", action="store_true", help="run the built-in tests")
    sub = parser.add_subparsers(dest="command")
    p_fetch = sub.add_parser("fetch", help="read title, description, h1 and robots from a page")
    p_fetch.add_argument("source", help="http(s) URL, HTML file, or - for stdin")
    p_check = sub.add_parser("check", help="check candidate titles and descriptions")
    p_check.add_argument("file", help="candidates JSON file, or - for stdin")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.command:
        parser.print_usage(sys.stderr)
        print("error: give fetch, check or --selftest", file=sys.stderr)
        return 2
    try:
        if args.command == "fetch":
            out = cmd_fetch(args.source)
        else:
            try:
                text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
            except OSError as e:
                raise InputError(f"cannot read {args.file}: {e.strerror}")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                raise InputError(f"not valid JSON: {e.msg} at line {e.lineno}")
            out = cmd_check(data)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FetchError as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 4
    except Exception as e:  # noqa: BLE001
        print(f"internal error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
