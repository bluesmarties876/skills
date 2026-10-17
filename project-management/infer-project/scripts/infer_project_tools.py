#!/usr/bin/env python3
"""infer_project_tools.py — platform-agnostic helpers for the infer-project runbook.

Two jobs, both deliberately mechanical. The *judgement* — which project a task
actually belongs to — stays with the model. These commands only remove the parts a
model is bad at: pulling a project list out of whatever shape an unfamiliar platform
returns, and scoring token overlap so the model reasons over a shortlist instead of
scanning every project by hand.

Standard library only. No credentials, no network calls — it reads JSON you already
fetched through whatever access the platform happens to have.

Commands:
    extract   Pull projects out of an arbitrary API response
    rank      Score projects against a task's text and print a ranked shortlist

Usage:
    python3 infer_project_tools.py extract projects.json
    python3 infer_project_tools.py extract projects.json --json
    python3 infer_project_tools.py extract --stdin < projects.json
    python3 infer_project_tools.py rank projects.json "Send denim copy to Anita"
    python3 infer_project_tools.py rank projects.json --task-file task.txt --top 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Keys platforms actually use
# --------------------------------------------------------------------------- #

NAME_KEYS = [
    "name", "title", "project_name", "projectname", "display_name", "displayname",
    "label", "text", "summary", "subject",
]
ID_KEYS = [
    "id", "gid", "uid", "uuid", "key", "project_id", "projectid",
    "board_id", "list_id", "space_id", "value",
]
DESC_KEYS = [
    "description", "notes", "desc", "details", "purpose", "summary",
    "project_description", "content", "body",
]

# Collection keys seen in the wild, used only as a hint — the recursive scan is
# what actually finds the projects, so an unlisted platform still works.
COLLECTION_HINTS = [
    "projects", "data", "items", "results", "values", "records", "rows",
    "boards", "lists", "spaces", "folders", "groups", "entries", "nodes", "edges",
]

# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #

def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in d.items()}


def _first(d: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
    low = _lower_keys(d)
    for k in keys:
        if k in low and low[k] not in (None, "", [], {}):
            return low[k]
    return None


def _flatten_scalar(v: Any) -> Optional[str]:
    """Turn a metadata value into one short line, or None if it is not useful."""
    if v is None or isinstance(v, (dict, list)):
        if isinstance(v, list):
            parts = [_flatten_scalar(x) for x in v]
            parts = [p for p in parts if p]
            return ", ".join(parts) if parts else None
        if isinstance(v, dict):
            # a nested entity often carries the useful label
            inner = _first(v, NAME_KEYS)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
            return None
        return None
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "false", "true"):
        return None
    return s


def looks_like_project(rec: Any) -> bool:
    if not isinstance(rec, dict):
        return False
    low = _lower_keys(rec)
    if not any(k in low for k in NAME_KEYS):
        return False
    # a record with ONLY an id and a name is still a project; require the name to
    # be a non-empty string so we don't pick up stray dicts.
    for k in NAME_KEYS:
        if k in low and isinstance(low[k], str) and low[k].strip():
            return True
    return False


def find_collections(obj: Any, path: str = "", depth: int = 0,
                     out: Optional[List[Tuple[str, List[Any]]]] = None) -> List[Tuple[str, List[Any]]]:
    """Recursively find every list of project-shaped dicts, with the path it sat at.

    Critically, a list that looks like projects is recorded *and* still descended
    into. Platforms nest their real work containers below a coarse outer level —
    ClickUp is spaces -> folders -> lists — and stopping at the first match would
    hide the level that actually holds the tasks.
    """
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            find_collections(v, f"{path}.{k}" if path else str(k), depth + 1, out)
    elif isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        all_projects = bool(dicts) and all(looks_like_project(x) for x in dicts)
        if all_projects:
            out.append((path or "<root>", dicts))
        # Always descend. When the level is itself project-shaped the path stays
        # clean ("spaces.folders.lists"); otherwise index the elements so a mixed
        # list (a GraphQL edge array, say) still reports where it came from.
        for i, x in enumerate(obj):
            child = path if all_projects else (f"{path}[{i}]" if path else f"[{i}]")
            find_collections(x, child, depth + 1, out)
    return out


def find_string_lists(obj: Any, path: str = "", depth: int = 0,
                      out: Optional[List[Tuple[str, List[str]]]] = None) -> List[Tuple[str, List[str]]]:
    """Find lists of plain strings — some platforms return bare project names."""
    if out is None:
        out = []
    if depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            find_string_lists(v, f"{path}.{k}" if path else str(k), depth + 1, out)
    elif isinstance(obj, list):
        strs = [x for x in obj if isinstance(x, str) and x.strip()]
        if strs and len(strs) == len(obj):
            out.append((path or "<root>", strs))
        else:
            for i, x in enumerate(obj):
                find_string_lists(x, f"{path}[{i}]" if path else f"[{i}]", depth + 1, out)
    return out


def normalise(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce one platform record to the fields the runbook cares about."""
    low = _lower_keys(rec)
    name = _first(rec, NAME_KEYS)
    pid = _first(rec, ID_KEYS)
    desc = _first(rec, DESC_KEYS)

    known = set(NAME_KEYS) | set(ID_KEYS) | set(DESC_KEYS)
    extras: Dict[str, str] = {}
    for k, v in low.items():
        if k in known or k in ("meta", "created_at", "updated_at", "createdat",
                               "updatedat", "at", "modified_at"):
            continue
        flat = _flatten_scalar(v)
        if flat and len(flat) <= 160:
            extras[k] = flat

    return {
        "id": str(pid) if pid is not None else "",
        "name": str(name).strip() if isinstance(name, str) else "",
        "description": str(desc).strip() if isinstance(desc, str) else "",
        "extras": extras,
    }


def choose_collection(collections: List[Tuple[str, List[Any]]],
                      prefer: Optional[str] = None) -> Tuple[str, List[Any]]:
    """Pick which collection holds the projects.

    Preference order: an explicit --key, then the *deepest* collection whose last
    path segment is a known container name, then the deepest overall. Depth is the
    tie-breaker because platforms nest their real work containers below a coarse
    outer level (ClickUp spaces -> folders -> lists); the leaf is where tasks live.
    """
    if not collections:
        return ("<none>", [])

    def depth(path: str) -> int:
        return len([s for s in path.replace("[", ".").split(".") if s])

    def last(path: str) -> str:
        return path.split(".")[-1].lower()

    if prefer:
        matches = [c for c in collections if last(c[0]) == prefer.lower()]
        if matches:
            return max(matches, key=lambda c: (depth(c[0]), len(c[1])))

    hinted = [c for c in collections if last(c[0]) in COLLECTION_HINTS]
    pool = hinted or collections
    return max(pool, key=lambda c: (depth(c[0]), len(c[1])))


# --------------------------------------------------------------------------- #
# Scoring — mechanical overlap only, as a shortlist for the model to reason over
# --------------------------------------------------------------------------- #

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "into", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "as", "if", "then", "so",
    "my", "our", "your", "their", "his", "her", "all", "any", "each", "some",
    "up", "out", "off", "over", "new", "get", "got", "make", "made", "do",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-/+]*")


def tokenise(text: str) -> List[str]:
    if not text:
        return []
    toks = [t.lower().strip("'-/+") for t in TOKEN_RE.findall(text)]
    return [t for t in toks if t and t not in STOPWORDS and len(t) > 1]


def _stem(t: str) -> str:
    """Crude singularisation so 'images' matches 'image', 'courses' matches 'course'."""
    for suffix in ("ies", "es", "s"):
        if t.endswith(suffix) and len(t) > len(suffix) + 2:
            if suffix == "ies":
                return t[: -len(suffix)] + "y"
            return t[: -len(suffix)]
    return t


def score_project(task_tokens: List[str], proj: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Weighted overlap. A name match is worth much more than a metadata match."""
    name_toks = {_stem(t) for t in tokenise(proj.get("name", ""))}
    desc_toks = {_stem(t) for t in tokenise(proj.get("description", ""))}
    extra_toks = {_stem(t) for t in tokenise(" ".join(proj.get("extras", {}).values()))}

    task_stems = [_stem(t) for t in task_tokens]
    task_set = set(task_stems)

    score = 0.0
    hits: List[str] = []

    for tok in task_set:
        if tok in name_toks:
            score += 3.0
            hits.append(tok)
        elif tok in desc_toks:
            score += 1.5
            hits.append(tok)
        elif tok in extra_toks:
            score += 1.0
            hits.append(tok)

    # A whole multi-word phrase from the project name appearing in the task is a
    # much stronger signal than any single shared token.
    name = (proj.get("name") or "").strip().lower()
    if len(name.split()) >= 2 and name and name in " ".join(task_tokens).lower():
        score += 4.0
        hits.append(name)

    # Normalise a little by project-name length so a long descriptive name does not
    # win purely by having more tokens available to match.
    if name_toks:
        score = score / (1 + 0.15 * max(0, len(name_toks) - 2))

    return round(score, 2), hits


def rank_projects(task: str, projects: List[Dict[str, Any]],
                  top: int = 5) -> List[Dict[str, Any]]:
    task_tokens = tokenise(task)
    scored = []
    for p in projects:
        s, hits = score_project(task_tokens, p)
        scored.append({
            "name": p.get("name", ""),
            "id": p.get("id", ""),
            "score": s,
            "matched": hits,
            "extras": p.get("extras", {}),
        })
    scored.sort(key=lambda r: (-r["score"], r["name"].lower()))
    return scored[:top]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_extract(path: str, projects: List[Dict[str, Any]]) -> str:
    lines = [f"collection: {path}", f"projects: {len(projects)}", ""]
    for p in projects:
        ident = p["id"] or "-"
        extra = "; ".join(f"{k}={v}" for k, v in p["extras"].items())
        line = f"- [{ident}] {p['name']}"
        if p["description"]:
            line += f" — {p['description'][:120]}"
        if extra:
            line += f"  ({extra[:160]})"
        lines.append(line)
    return "\n".join(lines)


def render_rank(task: str, ranked: List[Dict[str, Any]]) -> str:
    lines = [f"task: {task}", ""]
    if not ranked or ranked[0]["score"] == 0:
        lines.append("No project shares a single meaningful token with this task.")
        lines.append("Every candidate is a guess — ask rather than answer.")
        return "\n".join(lines)
    for i, r in enumerate(ranked, 1):
        ident = r["id"] or "-"
        hits = ", ".join(r["matched"][:6]) if r["matched"] else "—"
        lines.append(f"{i}. [{r['id'] or '-'}] {r['name']}  score={r['score']}  matched: {hits}")
    top = ranked[0]["score"]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    if second == 0:
        lines.append("")
        lines.append("Only one candidate scores at all — treat that as the answer, not a contest.")
    elif top >= second * 1.6:
        lines.append("")
        lines.append(f"Clear leader ({top} vs {second}).")
    else:
        lines.append("")
        lines.append(f"Close call ({top} vs {second}) — below the 1.6x bar, so ask.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _read_source(args) -> str:
    """Read the JSON payload.

    `path` is optional: omitted, '-' or --stdin all mean stdin. But when --stdin is
    set and a positional was given, that positional is *not* the payload — for
    `rank` it is the task text — so it must not be read as a filename.
    """
    path = getattr(args, "path", None)
    if getattr(args, "stdin", False) or not path or path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _load_projects(args) -> Tuple[str, List[Dict[str, Any]]]:
    """Read the payload and reduce it to a list of normalised projects.

    Falls back to plain-string lists, which some platforms return for project
    names, so a bare `["Denim Course", "Admin"]` is still usable.
    """
    raw = _read_source(args)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: input is not valid JSON: {exc}\n")
        raise SystemExit(2)

    collections = find_collections(data)
    if collections:
        path, rows = choose_collection(collections, getattr(args, "key", None))
        return path, [normalise(r) for r in rows]

    # No project-shaped dicts anywhere — try bare string lists.
    str_lists = find_string_lists(data)
    if str_lists:
        prefer = getattr(args, "key", None)
        if prefer:
            matches = [c for c in str_lists if c[0].split(".")[-1].lower() == prefer.lower()]
            path, rows = (matches[0] if matches else str_lists[0])
        else:
            path, rows = max(str_lists, key=lambda c: len(c[1]))
        return path, [{"id": "", "name": s, "description": "", "extras": {}} for s in rows]

    return ("<none>", [])


def cmd_extract(args) -> int:
    path, projects = _load_projects(args)

    if args.json:
        print(json.dumps({
            "collection": path,
            "count": len(projects),
            "projects": projects,
        }, indent=2, ensure_ascii=False))
    else:
        print(render_extract(path, projects))
        if not projects:
            print()
            print("No project list found. Check you passed the raw API response, not "
                  "a hand-picked field — and use --key if the platform nests its "
                  "projects under an unusual name.")
    return 0


def cmd_rank(args) -> int:
    # With --stdin the payload comes from stdin, so a single positional is the task
    # text, not a filename — argparse has already put it in `path`.
    if args.stdin and args.path and not args.task:
        args.task = args.path
        args.path = None

    path, projects = _load_projects(args)

    task = args.task
    if args.task_file:
        with open(args.task_file, "r", encoding="utf-8") as fh:
            task = fh.read().strip()
    if not task:
        sys.stderr.write(
            "error: no task text given. Pass it as a positional argument after the "
            "file, or use --task-file. With --stdin, the task must be passed as a "
            "positional or via --task-file, since stdin is the project payload.\n"
        )
        return 2

    if not projects:
        sys.stderr.write(
            "error: no projects found in the input. Pass the raw API response for the "
            "project list.\n"
        )
        return 2

    ranked = rank_projects(task, projects, top=args.top)

    if args.json:
        print(json.dumps({
            "task": task,
            "collection": path,
            "considered": len(projects),
            "ranked": ranked,
        }, indent=2, ensure_ascii=False))
    else:
        print(render_rank(task, ranked))
        print()
        print(f"({len(projects)} projects considered from '{path}')")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="infer_project_tools.py",
        description="Platform-agnostic project extraction and shortlisting for infer-project.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("extract", help="Pull projects out of an arbitrary API response")
    sp.add_argument("path", nargs="?", help="JSON file (omit or use - for stdin)")
    sp.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    sp.add_argument("--key", help="collection key to prefer, e.g. projects or boards")
    sp.add_argument("--json", action="store_true", help="structured output")
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("rank", help="Score projects against a task and shortlist them")
    sp.add_argument("path", nargs="?", help="JSON file (omit or use - for stdin)")
    sp.add_argument("task", nargs="?", help="the task name or description")
    sp.add_argument("--stdin", action="store_true",
                    help="read the project JSON from stdin (pass the task as a positional or --task-file)")
    sp.add_argument("--task-file", dest="task_file", help="read the task text from a file")
    sp.add_argument("--key", help="collection key to prefer")
    sp.add_argument("--top", type=int, default=5, help="how many candidates to show")
    sp.add_argument("--json", action="store_true", help="structured output")
    sp.set_defaults(func=cmd_rank)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
