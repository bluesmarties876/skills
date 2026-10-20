#!/usr/bin/env python3
"""Score software options for select-software.

Three subcommands, each reading one JSON file (or stdin with "-"):

  score  eliminate options that fail a must, rank the rest on weighted wants,
         and say whether the leader is clear, close or fragile to the weights
  ahp    derive want weights from a pairwise matrix, with a consistency ratio
  tco    total each option's cost of ownership per year and over the horizon

Standard library only. No network calls, no credentials. Python 3.9 or later.
Exit 0 on a result, 1 when --selftest fails, 2 on bad usage or bad input,
3 on a defect in this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

CLOSE_MARGIN = 0.10
SENSITIVITY_STEP = 2
WEIGHT_MIN, WEIGHT_MAX = 1, 10
SCORE_MIN, SCORE_MAX = 0, 5
CR_LIMIT = 0.10
RECIPROCAL_TOLERANCE = 0.01
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
                7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
TCO_CATEGORIES = ("go-live", "run", "support", "upgrade", "exit", "internal-time")
SOURCES = ("verified", "vendor-stated")
KIND_NAMES = {int: "a whole number", str: "text", list: "a list", dict: "an object"}


class InputError(Exception):
    pass


def _load(path: str) -> Any:
    try:
        if path == "-":
            return json.load(sys.stdin)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError:
        raise InputError("cannot read " + path)
    except json.JSONDecodeError as err:
        raise InputError(path + " is not valid JSON: " + err.msg)


def _need(obj: Any, key: str, kind: type, where: str) -> Any:
    if not isinstance(obj, dict):
        raise InputError(where + " must be an object")
    if key not in obj:
        raise InputError(where + " has no " + repr(key))
    value = obj[key]
    if kind is int and isinstance(value, bool):
        raise InputError(where + "." + key + " must be a whole number")
    if not isinstance(value, kind):
        raise InputError("%s.%s must be %s" % (where, key, KIND_NAMES.get(kind, "of another type")))
    return value


def _list(obj: dict, key: str, where: str) -> list:
    value = obj.get(key, [])
    if not isinstance(value, list):
        raise InputError("%s.%s must be a list" % (where, key))
    return value


# ---------------------------------------------------------------- score

def _weights(data: dict) -> dict:
    wants = _need(data, "wants", list, "input")
    if not wants:
        raise InputError("input.wants is empty: weight at least one want before scoring")
    weights = {}
    for i, want in enumerate(wants):
        where = "wants[%d]" % i
        wid = _need(want, "id", str, where)
        weight = _need(want, "weight", int, where)
        if not WEIGHT_MIN <= weight <= WEIGHT_MAX:
            raise InputError("%s.weight is %d; weights run %d to %d"
                             % (where, weight, WEIGHT_MIN, WEIGHT_MAX))
        if wid in weights:
            raise InputError("want " + repr(wid) + " is listed twice")
        weights[wid] = weight
    return weights


def _total(scores: dict, weights: dict) -> float:
    return sum(weights[w] * scores[w] for w in weights)


def _leader(totals: dict) -> list:
    return sorted(totals, key=lambda name: (-totals[name], name))


def _declared_musts(data: dict) -> list:
    musts = []
    for i, must in enumerate(_list(data, "musts", "input")):
        mid = _need(must, "id", str, "musts[%d]" % i)
        if mid in musts:
            raise InputError("must " + repr(mid) + " is listed twice")
        musts.append(mid)
    return musts


def score(data: dict) -> dict:
    weights = _weights(data)
    declared = _declared_musts(data)
    options = _need(data, "options", list, "input")
    if not options:
        raise InputError("input.options is empty")
    max_total = SCORE_MAX * sum(weights.values())
    eliminated, unconfirmed, survivors, incomplete = [], [], {}, []
    vendor_stated, stated_wants = {}, {}
    seen = set()
    for i, option in enumerate(options):
        where = "options[%d]" % i
        name = _need(option, "name", str, where)
        if name in seen:
            raise InputError("option " + repr(name) + " is listed twice")
        seen.add(name)
        failed, unknown, answered = [], [], set()
        for j, must in enumerate(_list(option, "musts", where)):
            mwhere = "%s.musts[%d]" % (where, j)
            mid = _need(must, "id", str, mwhere)
            if mid not in declared:
                raise InputError("%s answers %r, which is not a declared must" % (mwhere, mid))
            if mid in answered:
                raise InputError("%s answers %r twice" % (where, mid))
            answered.add(mid)
            passed = must.get("pass")
            evidence = must.get("evidence", "")
            if evidence is None:
                evidence = ""
            if not isinstance(evidence, str):
                raise InputError(mwhere + ".evidence must be text")
            if passed is False:
                if not evidence.strip():
                    raise InputError(mwhere + " fails with no evidence; an elimination cites its evidence")
                failed.append({"must": mid, "evidence": evidence})
            elif passed is None:
                unknown.append(mid)
            elif passed is not True:
                raise InputError(mwhere + ".pass must be true, false or null")
        unknown.extend(m for m in declared if m not in answered)
        if failed:
            eliminated.append({"option": name, "failed": failed})
            continue
        if unknown:
            unconfirmed.append({"option": name, "unknown_musts": unknown})
            continue
        raw = option.get("scores", {})
        if not isinstance(raw, dict):
            raise InputError(where + ".scores must be an object keyed by want id")
        for wid in raw:
            if wid not in weights:
                raise InputError("%s scores %r, which is not a weighted want" % (where, wid))
        missing = [w for w in weights if w not in raw]
        if missing:
            incomplete.append({"option": name, "unscored_wants": missing})
            continue
        scores, stated = {}, []
        for wid, entry in raw.items():
            swhere = "%s.scores.%s" % (where, wid)
            value = _need(entry, "score", int, swhere)
            if not SCORE_MIN <= value <= SCORE_MAX:
                raise InputError("%s is %d; scores run %d to %d" % (swhere, value, SCORE_MIN, SCORE_MAX))
            source = entry.get("source")
            if source not in SOURCES:
                raise InputError("%s.source must be one of %s; every score says where it came from"
                                 % (swhere, ", ".join(SOURCES)))
            if source == "vendor-stated":
                stated.append(wid)
            scores[wid] = value
        survivors[name] = scores
        vendor_stated[name] = len(stated)
        stated_wants[name] = stated

    totals = {name: _total(s, weights) for name, s in survivors.items()}
    order = _leader(totals)
    ranking = [{"option": n, "total": totals[n],
                "percent": round(100.0 * totals[n] / max_total, 1),
                "vendor_stated_scores": vendor_stated[n]} for n in order]
    result = {"max_total": max_total, "ranking": ranking, "eliminated": eliminated,
              "unconfirmed": unconfirmed, "incomplete": incomplete,
              "flips": [], "margin_percent": None, "lead_rests_on_vendor_claims": None}

    if unconfirmed or incomplete:
        result["verdict"] = "INCOMPLETE"
        return result
    if not order:
        result["verdict"] = "NO_SURVIVORS"
        return result
    if len(order) == 1:
        result["verdict"] = "SINGLE_SURVIVOR"
        return result

    top, second = totals[order[0]], totals[order[1]]
    margin = (top - second) / top if top else 0.0
    result["margin_percent"] = round(100.0 * margin, 1)
    for wid in weights:
        for delta in (-SENSITIVITY_STEP, SENSITIVITY_STEP):
            changed = dict(weights)
            changed[wid] = min(WEIGHT_MAX, max(WEIGHT_MIN, weights[wid] + delta))
            if changed[wid] == weights[wid]:
                continue
            new_totals = {n: _total(s, changed) for n, s in survivors.items()}
            new_leader = _leader(new_totals)[0]
            if new_leader != order[0]:
                result["flips"].append({"want": wid, "weight": changed[wid],
                                        "leader": new_leader})
    leader = order[0]
    discounted = dict(survivors[leader])
    for wid in stated_wants[leader]:
        discounted[wid] = max(SCORE_MIN, discounted[wid] - 1)
    rival = max(t for n, t in totals.items() if n != leader)
    result["lead_rests_on_vendor_claims"] = _total(discounted, weights) <= rival
    if top == second:
        result["verdict"] = "TIE"
    elif margin < CLOSE_MARGIN:
        result["verdict"] = "CLOSE_CALL"
    elif result["flips"] or result["lead_rests_on_vendor_claims"]:
        result["verdict"] = "FRAGILE"
    else:
        result["verdict"] = "CLEAR_LEADER"
    return result


# ---------------------------------------------------------------- ahp

def ahp(data: dict) -> dict:
    criteria = _need(data, "criteria", list, "input")
    matrix = _need(data, "matrix", list, "input")
    n = len(criteria)
    if n < 2:
        raise InputError("ahp needs at least two criteria")
    if n > max(RANDOM_INDEX):
        raise InputError("ahp supports at most %d criteria; group them into a hierarchy" % max(RANDOM_INDEX))
    if len(set(criteria)) != n:
        raise InputError("a criterion is listed twice")
    if len(matrix) != n or any(not isinstance(r, list) or len(r) != n for r in matrix):
        raise InputError("matrix must be %d by %d, one row and column per criterion" % (n, n))
    for i in range(n):
        for j in range(n):
            v = matrix[i][j]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise InputError("matrix[%d][%d] must be a positive number" % (i, j))
        if abs(matrix[i][i] - 1) > RECIPROCAL_TOLERANCE:
            raise InputError("matrix[%d][%d] must be 1: a criterion equals itself" % (i, i))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j] * matrix[j][i] - 1) > RECIPROCAL_TOLERANCE:
                raise InputError("matrix[%d][%d] and matrix[%d][%d] are not reciprocals" % (i, j, j, i))

    vector = [1.0 / n] * n
    for _ in range(200):
        nxt = [sum(matrix[i][j] * vector[j] for j in range(n)) for i in range(n)]
        total = sum(nxt)
        nxt = [v / total for v in nxt]
        if max(abs(a - b) for a, b in zip(nxt, vector)) < 1e-12:
            vector = nxt
            break
        vector = nxt
    product = [sum(matrix[i][j] * vector[j] for j in range(n)) for i in range(n)]
    lambda_max = sum(product[i] / vector[i] for i in range(n)) / n
    ci = (lambda_max - n) / (n - 1)
    ri = RANDOM_INDEX[n]
    cr = ci / ri if ri else 0.0
    top = max(vector)
    return {
        "weights": {c: round(w, 4) for c, w in zip(criteria, vector)},
        "kt_weights": {c: max(WEIGHT_MIN, int(round(WEIGHT_MAX * w / top)))
                       for c, w in zip(criteria, vector)},
        "consistency_ratio": round(cr, 3),
        "consistent": cr <= CR_LIMIT,
    }


# ---------------------------------------------------------------- tco

def tco(data: dict) -> dict:
    years = _need(data, "horizon_years", int, "input")
    if years < 1:
        raise InputError("input.horizon_years must be at least 1")
    currency = data.get("currency", "")
    options = _need(data, "options", list, "input")
    if not options:
        raise InputError("input.options is empty")
    out = []
    for i, option in enumerate(options):
        where = "options[%d]" % i
        name = _need(option, "name", str, where)
        lines = _need(option, "lines", list, where)
        per_year = [0.0] * years
        by_category = {}
        items, duplicates = set(), []
        for j, line in enumerate(lines):
            lwhere = "%s.lines[%d]" % (where, j)
            item = _need(line, "item", str, lwhere)
            category = _need(line, "category", str, lwhere)
            if category not in TCO_CATEGORIES:
                raise InputError("%s.category must be one of %s" % (lwhere, ", ".join(TCO_CATEGORIES)))
            amounts = _need(line, "amounts", list, lwhere)
            if len(amounts) != years:
                raise InputError("%s has %d amounts; the horizon is %d years" % (lwhere, len(amounts), years))
            for k, amount in enumerate(amounts):
                if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
                    raise InputError("%s.amounts[%d] must be a number of zero or more" % (lwhere, k))
                per_year[k] += amount
            key = item.strip().lower()
            if key in items:
                duplicates.append(item)
            items.add(key)
            by_category[category] = by_category.get(category, 0.0) + sum(amounts)
        out.append({
            "option": name,
            "per_year": per_year,
            "total": sum(per_year),
            "by_category": by_category,
            "missing_categories": [c for c in TCO_CATEGORIES if c not in by_category],
            "possible_double_count": duplicates,
        })
    out.sort(key=lambda o: (o["total"], o["option"]))
    return {"currency": currency, "horizon_years": years, "options": out}


# ---------------------------------------------------------------- selftest

def _fixture(**overrides) -> dict:
    base = {
        "musts": [{"id": "sso"}],
        "wants": [{"id": "usability", "weight": 10}, {"id": "integration", "weight": 6}],
        "options": [
            {"name": "Option A", "musts": [{"id": "sso", "pass": True}],
             "scores": {"usability": {"score": 4}, "integration": {"score": 4}}},
            {"name": "Option B", "musts": [{"id": "sso", "pass": True}],
             "scores": {"usability": {"score": 2}, "integration": {"score": 3}}},
        ],
    }
    base.update(overrides)
    return base


def _sourced(data: dict) -> dict:
    for option in data.get("options", []):
        for entry in option.get("scores", {}).values():
            entry.setdefault("source", "verified")
    return data


def _expect_error(func, data) -> bool:
    try:
        func(data)
    except InputError:
        return True
    return False


def selftest() -> int:
    checks = []
    def run(data):
        return score(_sourced(data))

    def check(label, ok):
        checks.append((label, bool(ok)))

    d = _fixture()
    del d["options"][1]["musts"]
    r = run(d)
    check("an option silent on a declared must is unconfirmed",
          r["verdict"] == "INCOMPLETE" and r["unconfirmed"][0]["unknown_musts"] == ["sso"])

    d = _fixture()
    d["options"][0]["musts"] = [{"id": "gdpr", "pass": True}]
    check("an undeclared must is refused", _expect_error(run, d))

    d = _fixture()
    d["options"][1]["musts"] = [{"id": "sso", "pass": False, "evidence": 5}]
    check("non-text evidence is refused, not a crash", _expect_error(run, d))

    d = _fixture()
    d["options"][0]["musts"] = {"id": "sso"}
    check("musts as an object is refused", _expect_error(run, d))

    d = _fixture()
    d["options"][0]["scores"]["usability"]["source"] = "brochure"
    check("an unknown source is refused", _expect_error(run, d))
    check("a missing source is refused", _expect_error(score, _fixture()))

    d = _fixture()
    d["options"][0]["scores"] = {"usability": {"score": 4, "source": "vendor-stated"},
                                 "integration": {"score": 4, "source": "vendor-stated"}}
    d["options"][1]["scores"] = {"usability": {"score": 3}, "integration": {"score": 4}}
    r = run(d)
    check("a lead resting on vendor claims is fragile",
          r["verdict"] == "FRAGILE" and r["lead_rests_on_vendor_claims"] and not r["flips"])

    d = _fixture(wants=[{"id": "usability", "weight": 10}])
    d["options"][0]["scores"] = {"usability": {"score": 5, "source": "vendor-stated"}}
    d["options"][1]["scores"] = {"usability": {"score": 4}}
    d["options"][0]["name"], d["options"][1]["name"] = "Zed", "Abe"
    check("a vendor-claim cut that only ties the lead is fragile",
          run(d)["lead_rests_on_vendor_claims"] is True)

    r = run(_fixture())
    check("clear leader", r["verdict"] == "CLEAR_LEADER" and r["ranking"][0]["option"] == "Option A")

    d = _fixture()
    d["options"][1]["musts"] = [{"id": "sso", "pass": False, "evidence": "no SAML on any plan"}]
    r = run(d)
    check("failed must eliminates", r["eliminated"][0]["option"] == "Option B"
          and r["verdict"] == "SINGLE_SURVIVOR")

    d = _fixture()
    d["options"][1]["musts"] = [{"id": "sso", "pass": False}]
    check("elimination without evidence is refused", _expect_error(run, d))

    d = _fixture()
    for o in d["options"]:
        o["musts"] = [{"id": "sso", "pass": False, "evidence": "none"}]
    check("no survivors", run(d)["verdict"] == "NO_SURVIVORS")

    d = _fixture()
    d["options"][1]["scores"] = {"usability": {"score": 4}, "integration": {"score": 4}}
    check("tie", run(d)["verdict"] == "TIE")

    d = _fixture()
    d["options"][1]["scores"] = {"usability": {"score": 4}, "integration": {"score": 3}}
    check("close call", run(d)["verdict"] == "CLOSE_CALL")

    d = _fixture(wants=[{"id": "usability", "weight": 5}, {"id": "integration", "weight": 4}])
    d["options"][0]["scores"] = {"usability": {"score": 5}, "integration": {"score": 1}}
    d["options"][1]["scores"] = {"usability": {"score": 1}, "integration": {"score": 5}}
    r = run(d)
    check("fragile to one weight", r["verdict"] == "FRAGILE" and r["flips"])

    d = _fixture()
    d["options"][1]["musts"] = [{"id": "sso", "pass": None}]
    check("unknown must is incomplete", run(d)["verdict"] == "INCOMPLETE")

    d = _fixture()
    del d["options"][1]["scores"]["integration"]
    check("unscored want is incomplete", run(d)["verdict"] == "INCOMPLETE")

    check("weight out of range refused",
          _expect_error(run, _fixture(wants=[{"id": "usability", "weight": 11}])))
    check("empty wants refused", _expect_error(run, _fixture(wants=[])))

    consistent = ahp({"criteria": ["a", "b", "c"],
                      "matrix": [[1, 2, 4], [0.5, 1, 2], [0.25, 0.5, 1]]})
    check("consistent ahp", consistent["consistent"] and consistent["kt_weights"]["a"] == 10)
    inconsistent = ahp({"criteria": ["a", "b", "c"],
                        "matrix": [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]})
    check("inconsistent ahp flagged", not inconsistent["consistent"])
    check("non-reciprocal ahp refused",
          _expect_error(ahp, {"criteria": ["a", "b"], "matrix": [[1, 3], [3, 1]]}))

    t = tco({"horizon_years": 2, "options": [
        {"name": "Option A", "lines": [
            {"item": "Licences", "category": "run", "amounts": [100, 100]},
            {"item": "licences", "category": "run", "amounts": [0, 10]}]}]})
    o = t["options"][0]
    check("tco totals", o["total"] == 210 and o["per_year"] == [100, 110])
    check("tco flags missing categories", "exit" in o["missing_categories"])
    check("tco flags a possible double count", o["possible_double_count"] == ["licences"])
    check("tco wrong horizon refused", _expect_error(tco, {"horizon_years": 3, "options": [
        {"name": "x", "lines": [{"item": "y", "category": "run", "amounts": [1]}]}]}))

    failing = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(("ok    " if ok else "FAIL  ") + label)
    print("PASS: 0 failing" if not failing else "FAIL: %d failing" % len(failing))
    return 0 if not failing else 1


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="prove each verdict and refusal on planted inputs")
    sub = parser.add_subparsers(dest="command")
    for name in ("score", "ahp", "tco"):
        p = sub.add_parser(name)
        p.add_argument("input", help="JSON file, or - for stdin")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.command:
        parser.print_usage(sys.stderr)
        return 2
    try:
        data = _load(args.input)
        if not isinstance(data, dict):
            raise InputError(args.input + " must hold a JSON object")
        result = {"score": score, "ahp": ahp, "tco": tco}[args.command](data)
    except InputError as err:
        print("error: " + str(err), file=sys.stderr)
        return 2
    except Exception as err:  # a defect in this script, not in the input
        print("internal error: %s: %s" % (type(err).__name__, err), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
