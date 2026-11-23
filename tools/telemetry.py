#!/usr/bin/env python3
"""Read the bot's telemetry lines from a match's stdout.log.

    tools/telemetry.py STDOUT_LOG TAG [--player P] [--summary]

A line is `[TAG] {json}`; a value too long for the engine's print buffer
(debug_printf, 16384 bytes, source/lib/debug.cpp) is split by the bot into
`[TAG P i/n] <text>` parts, joined here. Prints one JSON value per line, or
a short summary of each STATE value with --summary.
"""
import argparse
import collections
import json
import re
import sys

WHOLE = re.compile(r"^\[([A-Z]+)\] (\{.*\})$")
PART = re.compile(r"^\[([A-Z]+) (\d+) (\d+)/(\d+)\] (.*)$")


def read(path, tag):
    """Yield the decoded values of TAG in order, parts joined."""
    pending = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            m = WHOLE.match(raw)
            if m and m.group(1) == tag:
                yield json.loads(m.group(2))
                continue
            m = PART.match(raw)
            if not m or m.group(1) != tag:
                continue
            player, i, n, text = int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
            if i == 1:
                pending[player] = []
            pending.setdefault(player, []).append(text)
            if i == n:
                parts = pending.pop(player)
                if len(parts) != n:
                    sys.exit(f"{path}: {tag} of player {player}: {len(parts)} parts of {n}")
                yield json.loads("".join(parts))


def summary(state):
    kinds = collections.Counter(s["type"] for s in state["supplies"])
    amounts = collections.Counter()
    for s in state["supplies"]:
        amounts[s["type"]] += float(s["amount"])
    return {
        "player": state["p"], "time": state["time"], "civ": state["civ"], "mapSize": state["mapSize"],
        "stock": state["stock"], "population": [state["population"], state["populationLimit"], state["populationMax"]],
        "units": collections.Counter(u["template"] for u in state["units"]),
        "structures": collections.Counter(s["template"] for s in state["structures"]),
        "supplies": {k: [kinds[k], amounts[k] if amounts[k] == float("inf") else round(amounts[k])] for k in sorted(kinds)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("tag")
    ap.add_argument("--player", type=int)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    for value in read(a.log, a.tag):
        if a.player is not None and value.get("p") != a.player:
            continue
        print(json.dumps(summary(value) if a.summary else value))


if __name__ == "__main__":
    main()
