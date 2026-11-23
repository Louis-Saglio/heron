#!/usr/bin/env python3
"""Measurements of the economic program (spec/economy.md §8, "Before the bot").

    tools/.venv/bin/python tools/lp_experiments.py STDOUT_LOG [STDOUT_LOG...] [--all-integer SECONDS]

For each state ([STATE] of the match's stdout.log): size of the program,
time and result of the relaxation, of the branch and bound on the unlocks
(the phase), and optionally of the program with every item whole (the
integrality gap); the schedule's first minutes, the prices, the work; and
the movement of the first-period decisions under small changes of the
state (stability).
"""
import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lp_economy  # noqa: E402
import telemetry  # noqa: E402

PLAN = {"tau": 300.0, "soldier_value": 1.0, "phase_value": 30.0}
GRID = [10.0] * 6 + [30.0] * 8 + [60.0] * 10


def load(path):
    return next(telemetry.read(path, "STATE"))


def describe(eco):
    kinds = {}
    for layer in eco.layers:
        kinds[layer.specific] = kinds.get(layer.specific, 0) + 1
    return {"groups": {lp_economy.zad.short(g.name): g.count for g in eco.groups.values()},
            "layers": kinds, "sites": [(s["kind"], s["resource"], round(s["rect"]["x"]), round(s["rect"]["z"]))
                                       for s in eco.sites],
            "items": len(eco.items)}


def summary(res):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()
            if k in ("status", "wall", "G", "cols", "rows", "nnz", "nodes", "gap", "iterations")}


def first_decisions(eco, res):
    work = {f"{g}/{k}": round(v, 2) for (g, k), v in sorted(eco.work(res).items())}
    return {"starts": eco.starts(res), "work": work}


def distance(a, b):
    """How far two first-period decisions are: items started and workers per (group, resource)."""
    starts = {n: v for n, v in a["starts"]}
    other = {n: v for n, v in b["starts"]}
    ds = sum(abs(starts.get(n, 0) - other.get(n, 0)) for n in set(starts) | set(other))
    dw = sum(abs(a["work"].get(n, 0) - b["work"].get(n, 0)) for n in set(a["work"]) | set(b["work"]))
    return round(ds, 3), round(dw, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--all-integer", type=float, default=0.0, help="time limit of the all-integer solve (0: skip)")
    ap.add_argument("--schedule", type=float, default=300.0, help="print the schedule up to this time (s)")
    a = ap.parse_args()
    for path in a.logs:
        state = load(path)
        eco = lp_economy.Economy(state, PLAN, GRID)
        print(f"== {path}: {state['civ']}", json.dumps(describe(eco)))
        relax = eco.solve("none")
        print("relaxation ", json.dumps(summary(relax)))
        unlock = eco.solve("unlocks")
        print("unlocks    ", json.dumps(summary(unlock)))
        print("prices t=0 ", json.dumps({k: round(v, 4) for k, v in (eco.prices(relax) or {}).items()}))
        print("first      ", json.dumps(first_decisions(eco, unlock)))
        for t, name, v in eco.schedule(unlock):
            if t <= a.schedule:
                print(f"  {t:6.0f} s  {v:6.3f}  {name}")
        if a.all_integer:
            whole = eco.solve("all", time_limit=a.all_integer)
            gap = (unlock["G"] - whole["G"]) / unlock["G"] if unlock["G"] else 0.0
            print("all whole  ", json.dumps(summary(whole)), f"integrality gap {gap:.2%}")
        base = first_decisions(eco, unlock)
        for label, change in (("+10 wood", lambda s: s["stock"].__setitem__("wood", s["stock"]["wood"] + 10)),
                              ("+10 food", lambda s: s["stock"].__setitem__("food", s["stock"]["food"] + 10)),
                              ("-1 tree", lambda s: s["supplies"].remove(next(x for x in s["supplies"]
                                                                              if x["type"] == "wood.tree")))):
            s2 = copy.deepcopy(state)
            change(s2)
            eco2 = lp_economy.Economy(s2, PLAN, GRID)
            r2 = eco2.solve("unlocks")
            print(f"stability {label:9s} G {r2['G']:.3f} (base {unlock['G']:.3f}), first-period change "
                  f"(items, workers) {distance(base, first_decisions(eco2, r2))}")


if __name__ == "__main__":
    main()
