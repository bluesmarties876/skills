#!/usr/bin/env python3
"""resolve_repo_skill.py — find a skill's folder in a git repo, by name.

    python3 resolve_repo_skill.py <owner>/<repo> <skill-name>
    python3 resolve_repo_skill.py <skill-name>          # repo from SKILL_REPO

Flags:
    --read          print the skill's SKILL.md instead of the summary
    --ref=REF       branch or sha to resolve against (default: main, then the
                    repo's own default branch)
    --path=FOLDER   disambiguate when two folders share the skill's leaf name
    --fetch=DIR     download every file in the skill's folder into DIR, keeping
                    the folder's own layout (scripts/, references), so its
                    scripts can be run locally; prints each file written

The repo coordinate is taken from the first positional argument when it
contains a "/", and otherwise from the SKILL_REPO environment variable, so one
copy of this script can be bound to one repo.

GITHUB_TOKEN is optional. Public repos need no credentials at all; a token is
needed for private repos and raises GitHub's unauthenticated limit of 60
requests/hour. The token is never printed, and it is sent only to the API host
named below — never to a second host. A credential belongs to the host that
issues it: a host that does not expect the header rejects the request outright
rather than ignoring it, and GitHub reports that rejection as a 404, which
reads as a missing file. Every request, the --read file fetch included, is
therefore made through that one host.
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlparse

API = "https://api.github.com"

# Ask the contents endpoint for the file body itself, not a JSON envelope.
RAW_ACCEPT = "application/vnd.github.raw"

REPO_ENV = "SKILL_REPO"
TOKEN_ENV = "GITHUB_TOKEN"


def host_of(url):
    """The host a URL points at, lowercased — no scheme, path or query."""
    return (urlparse(url).hostname or "").lower()


# The one host this script talks to, and the only host the token is sent to.
API_HOST = host_of(API)


def die(msg, code=2):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(code)


def env_value(name):
    """Read an env var, treating blank/whitespace as unset."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    raw = raw.strip()
    return raw or None


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _headers(text):
    """Keep the last header block, so redirect chains resolve to the final one."""
    out = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("HTTP/"):
            out = {}
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            out[key.strip().lower()] = val.strip()
    return out


def curl(url, auth=True, accept=None):
    """GET url -> (status, body, headers).

    The token is attached only when the URL is on API_HOST, so a credential is
    never sent to a host that did not issue it. Pass auth=False to skip it even
    there. `accept` sets the Accept header, used to ask the contents endpoint
    for a raw file body instead of JSON. Never prints or echoes the token.
    """
    cmd = ["curl", "-sSL", "--max-time", "30", "-w", "%{http_code}"]
    token = env_value(TOKEN_ENV)
    if auth and token and host_of(url) == API_HOST:
        cmd += ["-H", "Authorization: Bearer " + token]
    if accept:
        cmd += ["-H", "Accept: " + accept]

    with tempfile.TemporaryDirectory() as td:
        header_path = os.path.join(td, "headers")
        body_path = os.path.join(td, "body")
        proc = subprocess.run(
            cmd + ["-D", header_path, "-o", body_path, url],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            reason = proc.stderr.strip() or "curl exit %d" % proc.returncode
            die("could not reach GitHub (%s)" % reason)

        try:
            status = int(proc.stdout.strip().split()[-1])
        except (ValueError, IndexError):
            status = 0
        return status, _read(body_path), _headers(_read(header_path))


def explain(status, headers, body):
    """Turn a non-200 into a message that says what is actually wrong."""
    if status == 401:
        die("%s was rejected by GitHub (401) — the token is invalid or expired." % TOKEN_ENV)

    if status in (403, 429):
        if headers.get("x-ratelimit-remaining") == "0":
            when = ""
            reset = headers.get("x-ratelimit-reset")
            if reset and reset.isdigit():
                stamp = datetime.datetime.utcfromtimestamp(int(reset))
                when = " It resets at %s UTC." % stamp.strftime("%H:%M")
            if env_value(TOKEN_ENV):
                die("GitHub rate limit exhausted on this token.%s" % when)
            die(
                "GitHub rate limit exhausted — unauthenticated requests share a "
                "limit of 60/hour per IP.%s Setting %s raises it." % (when, TOKEN_ENV)
            )
        die("GitHub refused the request (403). A token may lack access to this repo.")

    message = ""
    try:
        message = json.loads(body).get("message", "")
    except ValueError:
        pass
    die("GitHub returned HTTP %s%s" % (status, (": " + message) if message else ""))


def load_tree(owner, repo, ref):
    """Return the recursive tree, or None when that ref does not exist."""
    url = "%s/repos/%s/%s/git/trees/%s?recursive=1" % (API, owner, repo, ref)
    status, body, headers = curl(url)
    if status == 200:
        return json.loads(body)
    if status == 404:
        return None
    explain(status, headers, body)


def default_branch(owner, repo):
    status, body, _ = curl("%s/repos/%s/%s" % (API, owner, repo))
    if status != 200:
        return None
    return json.loads(body).get("default_branch")


def read_file(owner, repo, ref, repo_path):
    """Read one repo file at `ref` through the API host -> its text.

    Asks without the token first, then retries with it on 404, because 404
    means "no such file" OR "credential rejected" and the two cannot be told
    apart from the status alone.
    """
    url = "%s/repos/%s/%s/contents/%s?ref=%s" % (
        API, owner, repo, quote(repo_path, safe="/"), quote(ref, safe=""),
    )
    status, body, headers = curl(url, auth=False, accept=RAW_ACCEPT)
    if status == 404 and env_value(TOKEN_ENV):
        status, body, headers = curl(url, auth=True, accept=RAW_ACCEPT)
    if status != 200:
        if status in (401, 403):
            die("%s was rejected by %s (HTTP %d) while reading %s at ref '%s'."
                % (TOKEN_ENV, API_HOST, status, repo_path, ref))
        if status == 404:
            die(
                "cannot read %s at ref '%s' — GitHub returned 404, which means either "
                "no such file at that ref, or a credential %s was rejected; a private "
                "repo needs a valid token." % (repo_path, ref, TOKEN_ENV)
            )
        die("could not read %s at ref '%s' (HTTP %s)" % (repo_path, ref, status))
    return body


def fetch_file(owner, repo, ref, repo_path, dest):
    """Download one repo file's exact bytes to `dest` through the API host."""
    url = "%s/repos/%s/%s/contents/%s?ref=%s" % (
        API, owner, repo, quote(repo_path, safe="/"), quote(ref, safe=""),
    )
    for auth in (False, True):
        if auth and not env_value(TOKEN_ENV):
            break
        cmd = ["curl", "-sSL", "--max-time", "60", "-w", "%{http_code}",
               "-H", "Accept: " + RAW_ACCEPT, "-o", dest]
        token = env_value(TOKEN_ENV)
        if auth and token and host_of(url) == API_HOST:
            cmd += ["-H", "Authorization: Bearer " + token]
        proc = subprocess.run(cmd + [url], capture_output=True, text=True)
        if proc.returncode != 0:
            die("could not reach GitHub (%s)" % (proc.stderr.strip() or "curl exit %d" % proc.returncode))
        try:
            status = int(proc.stdout.strip().split()[-1])
        except (ValueError, IndexError):
            status = 0
        if status == 200:
            return
        if status != 404:
            break
    if os.path.exists(dest):
        os.remove(dest)
    die("could not download %s at ref '%s' (HTTP %s)" % (repo_path, ref, status))


def find(tree, skill):
    """Every (folder, files) whose leaf folder name is `skill`."""
    matches = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if not path.endswith("/SKILL.md"):
            continue
        folder = path[: -len("/SKILL.md")]
        if folder.split("/")[-1] != skill:
            continue
        prefix = folder + "/"
        files = sorted(
            i["path"][len(prefix):]
            for i in tree
            if i.get("type") == "blob" and i["path"].startswith(prefix)
        )
        matches.append((folder, files))
    return matches


def main():
    ref = path = None
    read = False
    fetch_dir = None
    positional = []

    for arg in sys.argv[1:]:
        if arg == "--read":
            read = True
        elif arg.startswith("--ref="):
            ref = arg[len("--ref="):].strip() or None
        elif arg.startswith("--fetch="):
            fetch_dir = arg[len("--fetch="):].strip() or None
            if not fetch_dir:
                die("--fetch needs a directory, e.g. --fetch=./my-skill")
        elif arg.startswith("--path="):
            path = arg[len("--path="):].strip().strip("/") or None
        elif arg.startswith("--"):
            die("unknown flag: %s" % arg)
        else:
            positional.append(arg)

    # A repo coordinate always contains "/", a skill name never does.
    if positional and "/" in positional[0]:
        coord, rest = positional[0], positional[1:]
    else:
        coord, rest = env_value(REPO_ENV), positional

    if len(rest) > 1:
        die("too many arguments — expected a skill name, got: %s" % " ".join(rest))
    skill = rest[0] if rest else None

    if not coord:
        die(
            "no repo given — pass <owner>/<repo> as the first argument, or set "
            "%s in this skill's settings" % REPO_ENV
        )
    if "/" not in coord:
        die("give the repo as <owner>/<repo>, got: %s" % coord)
    if not skill:
        die("no skill name given — usage: resolve_repo_skill.py [<owner>/<repo>] <skill-name>")

    owner, repo = coord.split("/", 1)
    repo = repo.rstrip("/")
    if not owner or not repo:
        die("give the repo as <owner>/<repo>, got: %s" % coord)

    # Resolve the tree. Default to main, then fall back to the repo's own
    # default branch so a master-default repo is not a mystery 404.
    used_ref = ref or "main"
    data = load_tree(owner, repo, used_ref)
    if data is None and ref is None:
        fallback = default_branch(owner, repo)
        if fallback and fallback != used_ref:
            sys.stderr.write("note: no branch '%s'; using '%s'\n" % (used_ref, fallback))
            used_ref = fallback
            data = load_tree(owner, repo, fallback)
    if data is None:
        die("cannot read %s/%s at ref '%s' — no such repo, or no such branch" % (owner, repo, used_ref))

    if data.get("truncated"):
        die(
            "GitHub truncated the file tree for %s/%s, so this listing is incomplete "
            "and a 'not found' below would be unreliable. The repo is too large to "
            "resolve in one call." % (owner, repo)
        )

    matches = find(data.get("tree", []), skill)
    if not matches:
        names = sorted(
            {
                i["path"][: -len("/SKILL.md")].split("/")[-1]
                for i in data.get("tree", [])
                if i.get("type") == "blob" and i["path"].endswith("/SKILL.md")
            }
        )
        sys.stderr.write("error: no skill named '%s' in %s\n" % (skill, coord))
        if names:
            sys.stderr.write("available: %s\n" % ", ".join(names))
        return 1

    if path:
        matches = [m for m in matches if m[0] == path or m[0].endswith("/" + path)]
        if not matches:
            die("no folder matching '%s' holds a skill named '%s' in %s" % (path, skill, coord), 1)

    if len(matches) > 1:
        sys.stderr.write(
            "error: '%s' is ambiguous in %s — %d folders share that name:\n"
            % (skill, coord, len(matches))
        )
        for folder, _ in matches:
            sys.stderr.write("  %s\n" % folder)
        sys.stderr.write("pick one with --path=<folder>\n")
        return 1

    folder, files = matches[0]

    if read and fetch_dir:
        die("use --read or --fetch, not both")

    if fetch_dir:
        root = os.path.abspath(fetch_dir)
        written = []
        for name in files:
            parts = name.split("/")
            if any(p in ("", ".", "..") for p in parts) or os.path.isabs(name):
                die("refusing an unsafe path in the repo listing: %s" % name)
            dest = os.path.join(root, *parts)
            if os.path.commonpath([root, os.path.abspath(dest)]) != root:
                die("refusing a path outside %s: %s" % (root, name))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            fetch_file(owner, repo, used_ref, folder + "/" + name, dest)
            written.append(dest)
        print("skill:  %s" % skill)
        print("repo:   %s" % coord)
        print("ref:    %s" % used_ref)
        print("folder: %s" % folder)
        print("fetched %d file(s) into %s:" % (len(written), root))
        for d in written:
            print("  %s" % d)
        print()
        print("Read %s first." % os.path.join(root, "SKILL.md"))
        return 0

    if read:
        # Read the file through the API host, at the resolved ref. A CDN host
        # does not expect this script's credential and rejects it, so the read
        # goes to the host that issued the token. See the module docstring.
        body = read_file(owner, repo, used_ref, folder + "/SKILL.md")
        sys.stdout.write(body)
        return 0

    print("skill:  %s" % skill)
    print("repo:   %s" % coord)
    print("folder: %s" % folder)
    print("read:   %s/SKILL.md" % folder)
    others = [f for f in files if f != "SKILL.md"]
    if others:
        print("also in this folder:")
        for name in others:
            print("  %s" % name)
    print()
    print("Read %s/SKILL.md first." % folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
