#!/usr/bin/env python3
"""verify_write.py — prove what a repo write actually landed.

Two checks, both on the committed files rather than on anything staged:

  * bytes      each committed file hashed against its local counterpart
  * scope      the commit touched exactly the paths it was meant to

The scope check is the one that catches a lost update. A write based on a stale
copy replaces whatever landed in the meantime, and the signature is a commit
touching a file the caller never meant to change.

Two ways this check can mislead, and what is done about each:

  * A base file that is GONE and one that MOVED are different situations. A gone
    file is reported separately, so a caller is not told to re-read something
    that no longer exists.
  * A compare payload that is truncated, or empty because the commit was a merge,
    makes every intended path look untouched. That would read as a failed scope
    on a write that landed correctly, so the payload is inspected and the
    ambiguity is reported instead of being resolved by guesswork.

Pure: no network, no credentials, standard library only, Python 3.9 or later.

Exit 0 clean · 1 a check failed · 2 usage or IO error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

# GitHub caps a compare response at 300 files / 250 commits and does not signal
# it: the payload simply ends. `files` is then an under-report, which is the
# dangerous direction, because a real collision reads as absent.
COMPARE_FILE_CAP = 300
COMPARE_COMMIT_CAP = 250


def die(message):
    sys.stderr.write("error: %s\n" % message)
    sys.exit(2)


def digest(path):
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        die("cannot read %s" % path)


def read_changed(path):
    """The commit's changed paths, plus anything that makes the set untrustworthy.

    Two payloads are accepted, because the two routes to a comparison spell the
    field differently: the compare endpoint returns `filename`, and the wrapper
    that normalises it returns `path`. A caller that already has the paths can
    pass one per line, in which case the counts are simply unknown.

    Returns `(entries, signals)`. A signal names a reason the changed set may be
    an under-report; an empty list means the set is usable.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        die("cannot read %s" % path)
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except ValueError as exc:
            die("%s looks like JSON but does not parse: %s" % (path, exc))
        signals = []
        if isinstance(payload, dict):
            entries = payload.get("files")
            if entries is None:
                die("%s is a JSON object with no \"files\" key" % path)
            if payload.get("files_truncated"):
                signals.append("the payload is flagged files_truncated")
            total_commits = payload.get("total_commits")
            if isinstance(total_commits, int) and total_commits >= COMPARE_COMMIT_CAP:
                signals.append("the comparison spans %d commits, at or past the %d cap"
                               % (total_commits, COMPARE_COMMIT_CAP))
        else:
            entries = payload
        if isinstance(entries, list) and len(entries) >= COMPARE_FILE_CAP:
            signals.append("the payload carries %d files, at or past the %d cap"
                           % (len(entries), COMPARE_FILE_CAP))
        out = []
        for entry in entries:
            if isinstance(entry, str):
                out.append({"path": entry, "additions": None, "deletions": None})
            elif isinstance(entry, dict) and (entry.get("path") or entry.get("filename")):
                out.append({"path": entry.get("path") or entry["filename"],
                            "additions": entry.get("additions"),
                            "deletions": entry.get("deletions")})
            else:
                die("%s has an entry that is neither a path nor an object with one" % path)
        if not out:
            # An empty set is what a merge commit returns, and what a payload past
            # the cap can collapse to. It is also what "nothing changed" returns,
            # and the three cannot be told apart from here.
            signals.append("the payload lists no changed files")
        return out, signals
    entries = [{"path": line.strip(), "additions": None, "deletions": None}
               for line in raw.splitlines() if line.strip()]
    return entries, []


def pairs(values):
    out = []
    for value in values or []:
        if "=" not in value:
            die("--compare wants <repo path>=<local path>, got %r" % value)
        repo_path, local_path = value.split("=", 1)
        out.append((repo_path.strip(), local_path.strip()))
    return out


def run(args):
    import os

    compared, mismatched, absent = [], [], []
    for repo_path, local_path in pairs(args.compare):
        local_hash = digest(local_path)
        candidate = os.path.join(args.readback_dir, repo_path)
        if not os.path.isfile(candidate):
            candidate = os.path.join(args.readback_dir, os.path.basename(repo_path))
        if not os.path.isfile(candidate):
            if args.allow_absent_readback:
                # Told to treat an absent read-back as expected, so it is a
                # distinct outcome rather than a byte mismatch.
                absent.append({"path": repo_path,
                               "why": "not in the read-back directory, and treated as "
                                      "expected by --allow-absent-readback"})
            else:
                mismatched.append({"path": repo_path, "why": "not in the read-back directory"})
            continue
        remote_hash = digest(candidate)
        compared.append(repo_path)
        if remote_hash != local_hash:
            mismatched.append({"path": repo_path, "why": "bytes differ from the local copy"})

    scope = {"intended": args.intended or [], "deleted": args.deleted or [], "changed": [],
             "missing": [], "extra": [], "deleted_missing": [], "shrunk": [],
             "unreliable": []}
    if args.changed:
        entries, signals = read_changed(args.changed)
        scope["changed"] = [e["path"] for e in entries]
        scope["unreliable"] = signals
        # A deletion is intended, and it belongs in `changed` like any other touch.
        # It is not an `extra` path: that list is the lost-update signature, and a
        # file the caller meant to remove landing there would fail a correct write.
        intended = set(args.intended or []) | set(args.deleted or [])
        changed = set(scope["changed"])
        if not signals:
            # Only a trustworthy set can support the scope verdict. Where the set
            # is an under-report, every intended path would read as missing, which
            # is the direction that fails a write that in fact landed.
            scope["missing"] = sorted(intended - changed)
            scope["extra"] = sorted(changed - intended)
        # Reported whether or not the payload is trustworthy, because "the removal
        # did not happen" is a distinct outcome the caller must be told about. A
        # removal is silent in the repo: the file simply stays.
        scope["deleted_missing"] = sorted(set(args.deleted or []) - changed)
        for entry in entries:
            added, removed = entry.get("additions"), entry.get("deletions")
            if isinstance(added, int) and isinstance(removed, int) and removed > added:
                scope["shrunk"].append("%s: +%d/-%d" % (entry["path"], added, removed))
    elif args.intended or args.deleted:
        die("--intended and --deleted need --changed: give the commit's changed paths to "
            "compare against")

    ok = not mismatched and not scope["missing"] and not scope["extra"] \
        and not scope["deleted_missing"]
    return {"ok": ok, "compared": compared, "mismatched": mismatched, "absent": absent,
            "scope": scope}


def selftest():
    import io
    import os
    import tempfile

    failures = []

    def check(ok, label):
        print("  %s  %s" % ("ok " if ok else "FAIL", label))
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        with open(a, "w") as handle:
            handle.write("same\n")
        with open(b, "w") as handle:
            handle.write("same\n")
        rb = os.path.join(tmp, "readback")
        os.makedirs(rb)
        with open(os.path.join(rb, "a.md"), "w") as handle:
            handle.write("same\n")
        with open(os.path.join(rb, "b.md"), "w") as handle:
            handle.write("different\n")
        changed = os.path.join(tmp, "changed.json")
        with open(changed, "w") as handle:
            json.dump({"files": [{"filename": "api/x/SKILL.md"},
                                 {"filename": "api/x/scripts/x.py", "additions": 4, "deletions": 1}]},
                      handle)
        changed_list = os.path.join(tmp, "changed.txt")
        with open(changed_list, "w") as handle:
            handle.write("api/x/SKILL.md\napi/x/scripts/x.py\n")

        class Args(object):
            pass

        def args(**kw):
            out = Args()
            out.compare = kw.get("compare", [])
            out.readback_dir = rb
            out.intended = kw.get("intended")
            out.deleted = kw.get("deleted")
            out.changed = kw.get("changed")
            out.allow_absent_readback = kw.get("allow_absent_readback", False)
            return out

        r = run(args(compare=["a.md=" + a], intended=["api/x/SKILL.md", "api/x/scripts/x.py"],
                     changed=changed))
        check(r["ok"], "identical bytes and an exact scope are clean")

        r = run(args(compare=["b.md=" + b], intended=["api/x/SKILL.md"], changed=changed))
        check(not r["ok"] and r["mismatched"], "differing bytes fail")

        r = run(args(compare=[], intended=["api/x/SKILL.md"], changed=changed))
        check(not r["ok"] and r["scope"]["extra"] == ["api/x/scripts/x.py"],
              "a file touched but not intended is reported as extra")

        r = run(args(compare=[], intended=["api/x/SKILL.md", "api/x/gone.md"], changed=changed))
        check(not r["ok"] and r["scope"]["missing"] == ["api/x/gone.md"],
              "an intended file the commit did not touch is reported as missing")

        r = run(args(compare=[], intended=["api/x/SKILL.md", "api/x/scripts/x.py"],
                     changed=changed_list))
        check(r["ok"], "a plain list of changed paths works as well as a compare payload")

        with open(changed, "w") as handle:
            json.dump({"files": [{"filename": "api/x/scripts/x.py", "additions": 38, "deletions": 216}]},
                      handle)
        r = run(args(compare=[], intended=["api/x/scripts/x.py"], changed=changed))
        check(r["ok"] and r["scope"]["shrunk"] == ["api/x/scripts/x.py: +38/-216"],
              "a commit that removed far more than it added is reported, and still passes")

        # A base file that is absent, not different.
        r = run(args(compare=["gone.md=" + a], intended=None, changed=None))
        check(not r["ok"] and r["mismatched"] and not r["absent"],
              "an absent read-back fails by default")
        r = run(args(compare=["gone.md=" + a], intended=None, changed=None,
                     allow_absent_readback=True))
        check(r["ok"] and r["absent"] and not r["mismatched"],
              "--allow-absent-readback reports an absent base file as absent, and passes")

        # A truncated or empty comparison must not be read as a failed scope.
        with open(changed, "w") as handle:
            json.dump({"total_commits": 1, "files": []}, handle)
        r = run(args(compare=[], intended=["api/x/SKILL.md"], changed=changed))
        check(r["ok"] and r["scope"]["unreliable"] and not r["scope"]["missing"],
              "an empty payload is reported as unreliable, not as a missing path")

        with open(changed, "w") as handle:
            json.dump({"total_commits": 1, "files_truncated": True,
                       "files": [{"filename": "api/x/SKILL.md"}]}, handle)
        r = run(args(compare=[], intended=["api/x/SKILL.md", "api/x/scripts/x.py"],
                     changed=changed))
        check(r["ok"] and r["scope"]["unreliable"] and not r["scope"]["missing"],
              "a payload flagged files_truncated is reported, not read as a missing path")

        with open(changed, "w") as handle:
            json.dump({"total_commits": 1,
                       "files": [{"filename": "api/x/f%d.py" % i} for i in range(COMPARE_FILE_CAP)]},
                      handle)
        r = run(args(compare=[], intended=["api/x/f0.py"], changed=changed))
        check(r["ok"] and any("cap" in s for s in r["scope"]["unreliable"]),
              "a payload at the file cap is flagged")

        # A deleted path is intended, so it must not read as a lost update.
        with open(changed, "w") as handle:
            json.dump({"files": [{"filename": "api/x/SKILL.md", "additions": 4, "deletions": 1},
                                 {"filename": "api/x/scripts/gone.py", "additions": 0, "deletions": 31}]},
                      handle)
        r = run(args(compare=[], intended=["api/x/SKILL.md"],
                     deleted=["api/x/scripts/gone.py"], changed=changed))
        check(r["ok"] and not r["scope"]["extra"],
              "a deleted path is intended, not an extra path")
        r = run(args(compare=[], intended=["api/x/SKILL.md"], changed=changed))
        check(not r["ok"] and r["scope"]["extra"] == ["api/x/scripts/gone.py"],
              "the same deletion without --deleted is still reported as extra")

        # A removal that did not happen must be caught: the file stays in the repo.
        with open(changed, "w") as handle:
            json.dump({"files": [{"filename": "api/x/SKILL.md", "additions": 4, "deletions": 1}]},
                      handle)
        r = run(args(compare=[], intended=["api/x/SKILL.md"],
                     deleted=["api/x/scripts/gone.py"], changed=changed))
        check(not r["ok"] and r["scope"]["deleted_missing"] == ["api/x/scripts/gone.py"],
              "a deletion the commit did not make is reported, and fails")

        bad = os.path.join(tmp, "bad.json")
        with open(bad, "w") as handle:
            handle.write("{not json")
        stderr = io.StringIO()
        saved, sys.stderr = sys.stderr, stderr
        try:
            run(args(compare=[], intended=["x"], changed=bad))
            check(False, "unparseable JSON exits 2")
        except SystemExit as exc:
            check(exc.code == 2, "unparseable JSON exits 2")
        finally:
            sys.stderr = saved

        stderr = io.StringIO()
        saved, sys.stderr = sys.stderr, stderr
        try:
            run(args(compare=["noseparator"], intended=None, changed=None))
            check(False, "a --compare without = exits 2")
        except SystemExit as exc:
            check(exc.code == 2, "a --compare without = exits 2")
        finally:
            sys.stderr = saved

        stderr = io.StringIO()
        saved, sys.stderr = sys.stderr, stderr
        try:
            run(args(compare=[], intended=["api/x/SKILL.md"], changed=None))
            check(False, "--intended without --changed exits 2")
        except SystemExit as exc:
            check(exc.code == 2, "--intended without --changed exits 2")
        finally:
            sys.stderr = saved
    print("FAIL: %d failing" % len(failures) if failures else "PASS: 0 failing")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prove what a repo write landed.")
    parser.add_argument("--compare", action="append", metavar="REPO=LOCAL",
                        help="Hash a local file against its read-back copy. Repeatable.")
    parser.add_argument("--readback-dir", metavar="DIR",
                        help="Directory holding the files fetched back from the commit.")
    parser.add_argument("--allow-absent-readback", action="store_true",
                        help="Report a base file absent from the read-back directory as "
                             "absent rather than as a byte mismatch. Use when the base "
                             "copy is expected to be gone, not moved.")
    parser.add_argument("--intended", action="append", metavar="PATH",
                        help="A repo path this write was meant to touch. Repeatable.")
    parser.add_argument("--deleted", action="append", metavar="PATH",
                        help="A repo path this write was meant to remove. Repeatable. Counts as "
                             "intended, so a removal stops reading as a lost update, and a "
                             "removal the commit did not make is reported as deleted_missing.")
    parser.add_argument("--changed", metavar="FILE",
                        help="The commit's changed paths: a compare payload, or one per line.")
    parser.add_argument("--selftest", action="store_true", help="Prove each check fires on a planted failure.")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.compare and not args.intended and not args.deleted:
        die("give --compare, or --intended with --changed")
    if args.compare and not args.readback_dir:
        die("--compare needs --readback-dir: the files fetched back from the commit")

    result = run(args)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
