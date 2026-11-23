#!/usr/bin/env python3
"""Offline prototype of the economic program of spec/economy.md (§3-§6).

Builds the time-indexed linear program from a [STATE] line (tools/telemetry.py)
and the game data (tools/gamedata/zad.py), and solves it with HiGHS. It exists
to measure what the specification can only estimate (§8, "Before the bot"):
size, time per solve, branch and bound on the unlocks, integrality gap, and
how much the schedule moves between solves. tools/lp_experiments.py runs the
measurements.

Prototype scope, narrower than the specification (each to be lifted when the
measurement needs it):
- resources: trees, rocks, mines, bushes and fields; no hunting, fish,
  treasures, trickles or barter (no market in the village phase);
- dropsite candidates: storehouses and farmsteads at sites generated from
  the supplies (clusters next to the supplies with the largest walking loss),
  in own territory; placement legality against terrain and obstructions is
  not checked; each supply is drawn by at most one candidate;
- fields: at existing dropsites accepting food only, at most FIELDS_PER_DROPSITE
  each, gatherers at half the field's depth from the dropsite;
- crews: a fixed number of builders per building kind (CREW), instead of the
  n* of spec §6;
- the walk of a newly trained unit to its work is not counted.
"""
import dataclasses
import math
import os
import sys
import time

import highspy
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gamedata"))
import zad  # noqa: E402

RESOURCES = ("food", "wood", "stone", "metal")
GATHERED = ("wood.tree", "stone.rock", "metal.ore", "food.fruit")
FIELD_TYPE = "food.grain"
SMALL_SUPPLIES = ("wood.tree", "food.fruit")   # spec economy §3: layers of many small supplies
BUILD_TIME_MODIFIER = 0.7          # sim/templates/special/filter/foundation.xml
TERRITORY_MASK = 0x1F              # simulation/ai/petra/mapModule.js
FIELDS_PER_DROPSITE = 6            # prototype geometry (see module doc)
CREW = {"house": 2, "field": 2, "storehouse": 4, "farmstead": 4, "barracks": 4}
BATCH_SIZES = (1, 2, 3, 4, 5)


# ------------------------------------------------------------------ geometry

def edge_distance(px, pz, rect):
    """Distance from a point to a rotated rectangle {x, z, angle, w, d} (0 inside).

    Width along (cos a, -sin a), depth along (sin a, cos a): the engine's
    obstruction frame."""
    dx, dz = px - rect["x"], pz - rect["z"]
    a = rect["angle"]
    u = dx * math.cos(a) - dz * math.sin(a)
    v = dx * math.sin(a) + dz * math.cos(a)
    return math.hypot(max(abs(u) - rect["w"] / 2, 0.0), max(abs(v) - rect["d"] / 2, 0.0))


def supply_radius(s):
    sh = s.get("shape") or {}
    if "r" in sh:
        return sh["r"]
    return min(sh.get("w", 0), sh.get("d", 0)) / 2


def cycle_rate(gamma, capacity, speed, d):
    """spec economy §2: r = C / (C / gamma + 2 d / v)."""
    if gamma <= 0 or capacity <= 0:
        return 0.0
    return capacity / (capacity / gamma + 2 * d / speed)


def decode_grid(g):
    out = np.empty(g["width"] * g["height"], dtype=np.int32)
    i = 0
    runs = g["runs"]
    for j in range(0, len(runs), 2):
        out[i:i + runs[j + 1]] = runs[j]
        i += runs[j + 1]
    return out.reshape(g["height"], g["width"])


# ------------------------------------------------------------------ game data

def num(t, path, default=0.0):
    v = t.text(path)
    return float(v) if v not in (None, "") else default


def classes_of(t):
    return set((t.text("Identity/Classes") or "").split()) | set((t.text("Identity/VisibleClasses") or "").split())


@dataclasses.dataclass
class Group:
    name: str
    count: int
    rates: dict          # specific type -> gather rate (BaseSpeed applied)
    capacity: dict       # generic -> carrying capacity
    speed: float
    build: float
    classes: set
    cost: dict = None
    train_time: float = 0.0
    pop: float = 1.0

    def gamma(self, specific):
        return self.rates.get(specific, self.rates.get(specific.split(".")[0], 0.0))

    def rate(self, specific, d, gamma_mult=1.0, cap_add=0.0):
        g = self.gamma(specific) * gamma_mult
        return cycle_rate(g, self.capacity.get(specific.split(".")[0], 0.0) + cap_add, self.speed, d)


def group_from_template(name, count=0):
    t = zad.template(name)
    base = num(t, "ResourceGatherer/BaseSpeed", 1.0)
    rates = {}
    node = t.get("ResourceGatherer/Rates")
    if node is not None:
        for k, n in node.children.items():
            if n.value:
                rates[k] = float(n.value) * base
    caps = {k: num(t, "ResourceGatherer/Capacities/" + k) for k in RESOURCES}
    speed = num(t, "UnitMotion/WalkSpeed") * num(t, "UnitMotion/WalkSpeedMultiplier", 1.0)
    return Group(name, count, rates, caps, speed, num(t, "Builder/Rate"), classes_of(t),
                 {k: num(t, "Cost/Resources/" + k) for k in RESOURCES}, num(t, "Cost/BuildTime"),
                 num(t, "Cost/Population", 1.0))


# ------------------------------------------------------------------ the model

@dataclasses.dataclass
class Layer:
    key: str
    specific: str
    amount: float        # math.inf for field places
    places: float
    d: float             # mean distance to its dropsite
    small: bool          # many small supplies: places shrink with the amount
    twin_of: int = -1    # index of the layer whose supplies it shares
    site: int = -1       # candidate dropsite that opens it
    field_place: int = 0 # j for the j-th place of fields (1..5), else 0
    field_site: str = ""  # dropsite key of the fields it belongs to


@dataclasses.dataclass
class Item:
    name: str
    kind: str            # train, build, tech, phase
    cost: dict
    duration: float
    queue: str = ""      # building kind it is made at ("" for buildings)
    pop: float = 0.0
    value: float = 0.0   # v_i per unit (spec README)
    upper: float = math.inf
    trains: str = ""     # group name
    batch: int = 0
    builds: str = ""     # house, storehouse, farmstead, field, barracks
    site: int = -1       # candidate dropsite index for storehouse/farmstead
    pop_bonus: float = 0.0
    village: bool = False
    modifications: list = None
    affects: list = None
    integer: bool = False
    field_site: str = ""


class Economy:
    """The program of spec economy §4 for one state, plan and grid."""

    def __init__(self, state, plan, grid, band=0.02, candidates=None):
        self.state, self.plan, self.grid, self.band = state, plan, grid, band
        self.player = state["p"]
        self.civ = state["civ"]
        self.own = zad.ownership(self.civ)
        self.periods = grid
        self.t = np.concatenate([[0.0], np.cumsum(grid)])
        self.P = len(grid)
        self.candidates_budget = candidates or {"wood": 4, "stone": 2, "metal": 2, "food": 2}
        self._groups()
        self._dropsites()
        self._sites()
        self._layers()
        self._items()

    # -- state

    def _groups(self):
        counts = {}
        for u in self.state["units"]:
            if u.get("rates"):
                counts[u["template"]] = counts.get(u["template"], 0) + 1
        cc = next(s["template"] for s in self.state["structures"] if "CivCentre" in s["classes"])
        self.cc_template = cc
        trainable = [n for n in zad.produced_by(cc, self.civ)[0]]
        self.barracks_template = next((n for n in zad.produced_by(self.civ_builder(), self.civ)[1]
                                       if n.endswith("/barracks")), None)
        barracks_units = zad.produced_by(self.barracks_template, self.civ)[0] if self.barracks_template else []
        names = sorted(set(counts) | set(trainable) | set(barracks_units))
        self.groups = {}
        for n in names:
            g = group_from_template(n, counts.get(n, 0))
            if g.rates:
                self.groups[n] = g
        self.trainable = {"cc": [n for n in trainable if n in self.groups],
                          "barracks": [n for n in barracks_units if n in self.groups]}

    def civ_builder(self):
        for u in self.state["units"]:
            if "Civilian" in u["classes"] or "Support" in u["classes"]:
                return u["template"]
        return self.state["units"][0]["template"]

    def _dropsites(self):
        self.dropsites = []
        for s in self.state["structures"]:
            if s["dropsite"] and s["foundation"] is None and s.get("shape") and "w" in s["shape"]:
                self.dropsites.append({"key": f"ds{s['id']}", "x": s["x"], "z": s["z"], "angle": s["angle"],
                                       "w": s["shape"]["w"], "d": s["shape"]["d"], "types": set(s["dropsite"])})
        self.territory = decode_grid(self.state["territory"])
        self.tcell = self.state["territory"]["cellSize"]
        self.supplies = [dict(s) for s in self.state["supplies"]
                         if s["type"] in GATHERED and s["owner"] == 0 and s["amount"] != "Infinity" and s["amount"] > 0]
        for s in self.supplies:
            k = s["type"].split(".")[0]
            best = min(((edge_distance(s["x"], s["z"], ds) - supply_radius(s), i)
                        for i, ds in enumerate(self.dropsites) if k in ds["types"]), default=(math.inf, -1))
            s["_d"] = max(best[0], 0.0)

    def owned(self, x, z):
        i, j = int(z / self.tcell), int(x / self.tcell)
        if 0 <= i < self.territory.shape[0] and 0 <= j < self.territory.shape[1]:
            return (int(self.territory[i, j]) & TERRITORY_MASK) == self.player
        return False

    def _sites(self):
        """Candidate dropsites: storehouse (wood, stone, metal), farmstead (food)."""
        self.sites = []
        ref = self.reference_group()
        builder = self.civ_builder()
        builds = zad.produced_by(builder, self.civ)[1]
        templ = {"storehouse": next((n for n in builds if n.endswith("/storehouse")), None),
                 "farmstead": next((n for n in builds if n.endswith("/farmstead")), None)}
        self.templates = templ
        cell = 24.0
        for k, kind in (("wood", "storehouse"), ("stone", "storehouse"), ("metal", "storehouse"),
                        ("food", "farmstead")):
            if not templ[kind]:
                continue
            t = zad.template(templ[kind])
            w, dd = num(t, "Footprint/Square/@width"), num(t, "Footprint/Square/@depth")
            mine = [s for s in self.supplies if s["type"].startswith(k + ".")]
            cells = {}
            for s in mine:
                if s["_d"] < 25 or "_site" in s:
                    continue
                key = (int(s["x"] // cell), int(s["z"] // cell))
                cells.setdefault(key, []).append(s)
            scored = []
            for key, ss in cells.items():
                amount = sum(s["amount"] for s in ss)
                cx = sum(s["x"] * s["amount"] for s in ss) / amount
                cz = sum(s["z"] * s["amount"] for s in ss) / amount
                gain = sum(s["amount"] * (ref.rate(s["type"], 3.0) - ref.rate(s["type"], s["_d"])) for s in ss)
                scored.append((gain, cx, cz))
            scored.sort(reverse=True)
            chosen = []
            for gain, cx, cz in scored:
                if len(chosen) >= self.candidates_budget[k]:
                    break
                site = self.place_site(cx, cz, w, dd, mine)
                if site is None or any(math.hypot(site[0] - c[0], site[1] - c[1]) < 40 for c in chosen):
                    continue
                chosen.append(site)
            for sx, sz in chosen:
                rect = {"x": sx, "z": sz, "angle": 0.0, "w": w, "d": dd}
                self.sites.append({"kind": kind, "resource": k, "rect": rect, "template": templ[kind],
                                   "index": len(self.sites)})
        for s in self.supplies:
            k = s["type"].split(".")[0]
            best = (s["_d"], -1)
            for site in self.sites:
                if site["resource"] != k and not (site["kind"] == "storehouse" and k in ("wood", "stone", "metal")):
                    continue
                d = max(edge_distance(s["x"], s["z"], site["rect"]) - supply_radius(s), 0.0)
                if d < best[0]:
                    best = (d, site["index"])
            if best[1] >= 0:
                s["_site"], s["_d2"] = best[1], best[0]

    def place_site(self, cx, cz, w, dd, mine):
        """Move from the cluster centre toward the nearest dropsite until clear of supplies."""
        ds = min(self.dropsites, key=lambda r: math.hypot(r["x"] - cx, r["z"] - cz))
        dx, dz = ds["x"] - cx, ds["z"] - cz
        n = math.hypot(dx, dz) or 1.0
        dx, dz = dx / n, dz / n
        half = math.hypot(w, dd) / 2 + 1.5
        near = [s for s in mine if math.hypot(s["x"] - cx, s["z"] - cz) < 80]
        for step in range(0, 60):
            x, z = cx + dx * step * 2, cz + dz * step * 2
            if all(math.hypot(s["x"] - x, s["z"] - z) > half + supply_radius(s) for s in near):
                return (x, z) if self.owned(x, z) else None
        return None

    def reference_group(self):
        civil = [g for g in self.groups.values() if "Civilian" in g.classes or "Support" in g.classes]
        return civil[0] if civil else next(iter(self.groups.values()))

    def _layers(self):
        """spec economy §3: fronts cut into bands of the reference group's rate."""
        ref = self.reference_group()
        buckets = {}
        for s in self.supplies:
            if not math.isfinite(s["_d"]):
                continue
            k = s["type"]
            small = k in SMALL_SUPPLIES
            b_old = int(ref.rate(k, s["_d"]) / self.band)
            site = s.get("_site", -1)
            b_new = int(ref.rate(k, s["_d2"]) / self.band) if site >= 0 else -1
            key = (k, small, b_old, site, b_new) if small else (k, False, s["id"], site, b_new)
            buckets.setdefault(key, []).append(s)
        self.layers = []
        for key, ss in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            k, small, _, site, _ = key
            amount = sum(s["amount"] for s in ss)
            d = sum(s["_d"] * s["amount"] for s in ss) / amount
            base = Layer(f"{k}:{len(self.layers)}", k, amount, sum(s["places"] for s in ss), d, small)
            self.layers.append(base)
            if site >= 0:
                d2 = sum(s["_d2"] * s["amount"] for s in ss) / amount
                self.layers.append(Layer(base.key + "'", k, amount, base.places, d2, small,
                                         twin_of=len(self.layers) - 1, site=site))
        field_t = zad.template(next(n for n in zad.produced_by(self.civ_builder(), self.civ)[1]
                                    if n.endswith("/field")))
        self.field_template = field_t
        self.field_rho = num(field_t, "ResourceSupply/DiminishingReturns", 1.0)
        self.field_places = int(num(field_t, "ResourceSupply/MaxGatherers"))
        field_d = num(field_t, "Footprint/Square/@depth") / 2
        for ds in self.dropsites:
            if "food" not in ds["types"]:
                continue
            for j in range(1, self.field_places + 1):
                self.layers.append(Layer(f"field:{ds['key']}:{j}", FIELD_TYPE, math.inf, 0.0, field_d, False,
                                         field_place=j, field_site=ds["key"]))

    def layer_rate(self, g, layer, gamma_mult=1.0, cap_add=0.0):
        if layer.field_place:
            gamma = g.gamma(FIELD_TYPE) * gamma_mult * self.field_rho ** (layer.field_place - 1)
            return cycle_rate(gamma, g.capacity.get("food", 0.0) + cap_add, g.speed, layer.d)
        return g.rate(layer.specific, layer.d, gamma_mult, cap_add)

    def _items(self):
        self.items = []
        cc_t = zad.template(self.cc_template)
        cc_batch = num(cc_t, "Trainer/BatchTimeModifier", 1.0)
        for n in self.trainable["cc"]:
            g = self.groups[n]
            soldier = "Soldier" in g.classes
            for b in BATCH_SIZES:
                self.items.append(Item(f"train {zad.short(n)} x{b} @cc", "train",
                                       {k: g.cost[k] * b for k in RESOURCES}, g.train_time * b ** cc_batch,
                                       queue="cc", pop=g.pop * b, value=self.plan["soldier_value"] * b if soldier else 0.0,
                                       trains=n, batch=b))
        if self.barracks_template:
            bt = zad.template(self.barracks_template)
            bb = num(bt, "Trainer/BatchTimeModifier", 1.0)
            for n in self.trainable["barracks"]:
                g = self.groups[n]
                for b in BATCH_SIZES:
                    self.items.append(Item(f"train {zad.short(n)} x{b} @barracks", "train",
                                           {k: g.cost[k] * b for k in RESOURCES}, g.train_time * b ** bb,
                                           queue="barracks", pop=g.pop * b,
                                           value=self.plan["soldier_value"] * b if "Soldier" in g.classes else 0.0,
                                           trains=n, batch=b))
        builds = zad.produced_by(self.civ_builder(), self.civ)[1]

        def building(kind, **kw):
            name = next((n for n in builds if n.endswith("/" + kind)), None)
            if not name:
                return None
            t = zad.template(name)
            crew = CREW[kind]
            dur = num(t, "Cost/BuildTime") / (crew ** BUILD_TIME_MODIFIER)
            return Item(kw.pop("label", kind), "build", {k: num(t, "Cost/Resources/" + k) for k in RESOURCES}, dur,
                        builds=kind, pop_bonus=num(t, "Population/Bonus"), village="Village" in classes_of(t), **kw)

        self.items.append(building("house", upper=40))
        if self.barracks_template:
            self.items.append(building("barracks", upper=2))
        for site in self.sites:
            it = building(site["kind"], label=f"{site['kind']} @site{site['index']} ({site['resource']})",
                          upper=1, site=site["index"])
            self.items.append(it)
        for ds in self.dropsites:
            if "food" in ds["types"]:
                self.items.append(building("field", label=f"field @{ds['key']}", upper=FIELDS_PER_DROPSITE,
                                           field_site=ds["key"]))
        techs = self.own.techs()
        researched = set(self.state["researched"])
        for name, producers in sorted(techs.items()):
            if not name.startswith("gather_") or name in researched:
                continue
            t = zad.tech(name)
            req = t.get("requirements") or {}
            if not zad.req_allows_civ(req, self.civ):
                continue
            if "phase_town" in str(req) or "phase_city" in str(req):
                continue
            mods = [m for m in t.get("modifications", []) if m["value"].startswith("ResourceGatherer/")]
            if not mods:
                continue
            kind = next(iter(producers)).split("/")[-1]
            if kind not in ("storehouse", "farmstead", "civil_centre"):
                continue
            self.items.append(Item(name, "tech", {k: t.get("cost", {}).get(k, 0) for k in RESOURCES},
                                   t.get("researchTime", 0), queue="cc" if kind == "civil_centre" else kind,
                                   upper=1, modifications=mods, affects=t.get("affects", [])))
        phase = next((n for n in techs if n.startswith("phase_town")), None)
        if phase:
            t = zad.tech(phase)
            self.items.append(Item(phase, "phase", {k: t.get("cost", {}).get(k, 0) for k in RESOURCES},
                                   t.get("researchTime", 0), queue="cc", value=self.plan["phase_value"], upper=1,
                                   integer=True))
            self.phase_village_needed = t.get("requirements", {}).get("entity", {}).get("number", 0)
        self.village0 = sum(1 for s in self.state["structures"]
                            if "Village" in classes_of(zad.template(s["template"])) and s["foundation"] is None)

    # -- the program

    def overlap(self, start, duration, p):
        a, b = self.t[start], self.t[start] + duration
        return max(0.0, min(b, self.t[p + 1]) - max(a, self.t[p]))

    def done_by(self, i, p):
        """Periods p' whose starts of item i are done by t_p."""
        d = self.items[i].duration
        return [q for q in range(self.P) if self.t[q] + d <= self.t[p] + 1e-9]

    def build(self, integer="unlocks", fix=None):
        """Assemble the program. integer: 'none', 'unlocks' or 'all'. fix: {(item, period): value}."""
        tau = self.plan["tau"]
        cols_cost, cols_lb, cols_ub, cols_int = [], [], [], []
        A_rows, A_cols, A_vals = [], [], []
        row_lb, row_ub = [], []
        self.col_names = []

        def col(name, cost=0.0, lb=0.0, ub=highspy.kHighsInf, is_int=False):
            cols_cost.append(cost)
            cols_lb.append(lb)
            cols_ub.append(ub)
            cols_int.append(is_int)
            self.col_names.append(name)
            return len(cols_cost) - 1

        def row(coefs, lb=-highspy.kHighsInf, ub=highspy.kHighsInf):
            r = len(row_lb)
            for c, v in coefs:
                if v != 0.0:
                    A_rows.append(r)
                    A_cols.append(c)
                    A_vals.append(v)
            row_lb.append(lb)
            row_ub.append(ub)
            return r

        G = list(self.groups.values())
        gi = {g.name: n for n, g in enumerate(G)}
        L = self.layers
        P = self.P
        # work x[g][l][p]
        self.x = {}
        for n, g in enumerate(G):
            for li, layer in enumerate(L):
                r = self.layer_rate(g, layer)
                if r <= 0:
                    continue
                for p in range(P):
                    self.x[n, li, p] = col(f"x {zad.short(g.name)} {layer.key} {p}")
        # builders' labour b[g][p] (worker equivalents)
        self.b = {(n, p): col(f"build {zad.short(g.name)} {p}") for n, g in enumerate(G) if g.build > 0 for p in range(P)}
        # items y[i][p]
        self.y = {}
        for i, it in enumerate(self.items):
            is_int = integer == "all" or (integer == "unlocks" and it.integer)
            for p in range(P):
                value = it.value * tau * math.exp(-(self.t[p] + it.duration) / tau) if it.value else 0.0
                ub = it.upper if math.isfinite(it.upper) else highspy.kHighsInf
                lb = 0.0
                if fix and (i, p) in fix:
                    lb = ub = fix[i, p]
                self.y[i, p] = col(f"y {it.name} {p}", -value, lb, ub, is_int)
        # technology extra output e[T][g][k][p]
        self.e = {}
        tech_items = [i for i, it in enumerate(self.items) if it.kind == "tech"]
        for i in tech_items:
            it = self.items[i]
            for n, g in enumerate(G):
                if it.affects and not any(a in g.classes for a in it.affects):
                    continue
                for k in RESOURCES:
                    gains = self.tech_gains(it, g, k)
                    if not gains:
                        continue
                    for p in range(P):
                        self.e[i, n, k, p] = col(f"e {it.name} {zad.short(g.name)} {k} {p}")
        # stock after purchases A[k][p]
        self.S = {(k, p): col(f"S {k} {p}") for k in RESOURCES for p in range(P)}
        # rows ---------------------------------------------------------------
        self.rows = {}
        stock0 = self.state["stock"]
        for k in RESOURCES:
            for p in range(P):
                coefs = [(self.S[k, p], 1.0)]
                if p > 0:
                    coefs.append((self.S[k, p - 1], -1.0))
                    dt = self.periods[p - 1]
                    for (n, li, q), c in self.x.items():
                        if q == p - 1 and L[li].specific.split(".")[0] == k:
                            coefs.append((c, -dt * self.layer_rate(G[n], L[li])))
                    for (i, n, kk, q), c in self.e.items():
                        if q == p - 1 and kk == k:
                            coefs.append((c, -dt))
                for i, it in enumerate(self.items):
                    if it.cost.get(k):
                        coefs.append((self.y[i, p], it.cost[k]))
                rhs = stock0.get(k, 0) if p == 0 else 0.0
                self.rows["stock", k, p] = row(coefs, rhs, rhs)
        # labour
        for n, g in enumerate(G):
            for p in range(P):
                coefs = [(c, 1.0) for (nn, li, q), c in self.x.items() if nn == n and q == p]
                if (n, p) in self.b:
                    coefs.append((self.b[n, p], 1.0))
                for i, it in enumerate(self.items):
                    if it.trains == g.name:
                        for q in self.done_by(i, p):
                            coefs.append((self.y[i, q], -it.batch))
                self.rows["labour", n, p] = row(coefs, ub=g.count)
        # builders: worker-seconds supplied >= crews' need
        for p in range(P):
            coefs = [(self.b[n, p], self.periods[p]) for n in range(len(G)) if (n, p) in self.b]
            for i, it in enumerate(self.items):
                if it.kind == "build":
                    for q in range(p + 1):
                        o = self.overlap(q, it.duration, p)
                        if o > 0:
                            coefs.append((self.y[i, q], -CREW[it.builds] * o))
            self.rows["crews", p] = row(coefs, lb=0.0)
        # places and amounts, with the amount taken from each layer and its twins
        # by the start of each period, Q[l][p] (spec economy §4, places and amounts)
        self.Q = {}
        for li, layer in enumerate(L):
            if layer.twin_of >= 0:
                continue
            twins = [li] + [lj for lj, other in enumerate(L) if other.twin_of == li]
            finite = math.isfinite(layer.amount)
            if finite:
                for p in range(1, P + 1):
                    self.Q[li, p] = col(f"Q {layer.key} {p}", ub=layer.amount)
                for p in range(P):
                    coefs = [(self.Q[li, p + 1], 1.0)]
                    if p > 0:
                        coefs.append((self.Q[li, p], -1.0))
                    coefs += [(self.x[n, lj, p], -self.periods[p] * self.layer_rate(G[n], L[lj]))
                              for lj in twins for n in range(len(G)) if (n, lj, p) in self.x]
                    self.rows["taken", li, p] = row(coefs, 0.0, 0.0)
            for p in range(P):
                coefs = [(self.x[n, lj, p], 1.0) for lj in twins for n in range(len(G)) if (n, lj, p) in self.x]
                if layer.field_place:
                    fi = [i for i, it in enumerate(self.items) if it.builds == "field" and it.field_site == layer.field_site]
                    for i in fi:
                        for q in self.done_by(i, p):
                            coefs.append((self.y[i, q], -1.0))
                    self.rows["places", li, p] = row(coefs, ub=0.0)
                    continue
                if layer.small and p > 0:
                    coefs.append((self.Q[li, p], layer.places / layer.amount))
                self.rows["places", li, p] = row(coefs, ub=layer.places)
        # twin layers open with their dropsite
        for lj, layer in enumerate(L):
            if layer.site < 0:
                continue
            i = next(i for i, it in enumerate(self.items) if it.site == layer.site)
            for p in range(P):
                coefs = [(self.x[n, lj, p], 1.0) for n in range(len(G)) if (n, lj, p) in self.x]
                coefs += [(self.y[i, q], -layer.places) for q in self.done_by(i, p)]
                self.rows["open", lj, p] = row(coefs, ub=0.0)
        # queues
        kinds = sorted({it.queue for it in self.items if it.queue})
        for qk in kinds:
            n0 = 1.0 if qk == "cc" else 0.0
            for p in range(P):
                coefs = []
                for i, it in enumerate(self.items):
                    if it.queue == qk:
                        for q in range(p + 1):
                            o = self.overlap(q, it.duration, p)
                            if o > 0:
                                coefs.append((self.y[i, q], o))
                    if it.builds == qk:
                        for q in self.done_by(i, p):
                            coefs.append((self.y[i, q], -self.periods[p]))
                self.rows["queue", qk, p] = row(coefs, ub=self.periods[p] * n0)
        # population
        for p in range(P):
            coefs = []
            for i, it in enumerate(self.items):
                if it.pop:
                    coefs += [(self.y[i, q], it.pop) for q in range(p + 1)]
                if it.pop_bonus:
                    coefs += [(self.y[i, q], -it.pop_bonus) for q in self.done_by(i, p)]
            self.rows["pop", p] = row(coefs, ub=self.state["populationLimit"] - self.state["population"])
        # the phase: Village structures done before it starts (zad: requirements entity class Village)
        phase = [i for i, it in enumerate(self.items) if it.kind == "phase"]
        for i in phase:
            for p in range(P):
                coefs = [(self.y[i, p], -self.phase_village_needed)]
                for j, it in enumerate(self.items):
                    if it.village:
                        coefs += [(self.y[j, q], 1.0) for q in self.done_by(j, p)]
                self.rows["phase", p] = row(coefs, lb=-self.village0)
            self.rows["phase once"] = row([(self.y[i, p], 1.0) for p in range(P)], ub=1.0)
        # item totals
        for i, it in enumerate(self.items):
            if math.isfinite(it.upper) and it.kind != "phase":
                self.rows["upper", i] = row([(self.y[i, p], 1.0) for p in range(P)], ub=it.upper)
        # technologies
        for (i, n, k, p), c in self.e.items():
            it, g = self.items[i], G[n]
            gains = self.tech_gains(it, g, k)
            coefs = [(c, 1.0)] + [(self.x[n, li, p], -gain) for li, gain in gains.items() if (n, li, p) in self.x]
            row(coefs, ub=0.0)
            ebar = max(gains.values()) * self.max_count(g)
            row([(c, 1.0)] + [(self.y[i, q], -ebar) for q in self.done_by(i, p)], ub=0.0)
        self.lp = highspy.HighsLp()
        self.lp.num_col_ = len(cols_cost)
        self.lp.num_row_ = len(row_lb)
        self.lp.col_cost_ = np.array(cols_cost)
        self.lp.col_lower_ = np.array(cols_lb)
        self.lp.col_upper_ = np.array(cols_ub)
        self.lp.row_lower_ = np.array(row_lb)
        self.lp.row_upper_ = np.array(row_ub)
        order = np.lexsort((np.array(A_rows), np.array(A_cols)))
        cols_sorted = np.array(A_cols)[order]
        self.lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        self.lp.a_matrix_.start_ = np.searchsorted(cols_sorted, np.arange(len(cols_cost) + 1)).astype(np.int32)
        self.lp.a_matrix_.index_ = np.array(A_rows, dtype=np.int32)[order]
        self.lp.a_matrix_.value_ = np.array(A_vals)[order]
        if any(cols_int):
            self.lp.integrality_ = [highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous
                                    for v in cols_int]
        self.nnz = len(A_vals)
        return self.lp

    def tech_gains(self, it, g, k):
        """Per layer of resource k: r' - r for group g with the technology."""
        out = {}
        for li, layer in enumerate(self.layers):
            spec = FIELD_TYPE if layer.field_place else layer.specific
            if spec.split(".")[0] != k:
                continue
            mult, add = 1.0, 0.0
            for m in it.modifications:
                path = m["value"]
                if path == "ResourceGatherer/Rates/" + spec or path == "ResourceGatherer/Rates/" + k:
                    mult *= m.get("multiply", 1.0)
                elif path == "ResourceGatherer/Capacities/" + k:
                    add += m.get("add", 0.0)
            if mult == 1.0 and add == 0.0:
                continue
            r0 = self.layer_rate(g, layer)
            if r0 <= 0:
                continue
            out[li] = self.layer_rate(g, layer, mult, add) - r0
        return out

    def max_count(self, g):
        return g.count + self.state["populationMax"] / max(g.pop, 1.0)

    def solve(self, integer="unlocks", fix=None, time_limit=60.0, basis=None, quiet=True):
        lp = self.build(integer, fix)
        h = highspy.Highs()
        if quiet:
            h.setOptionValue("output_flag", False)
        h.setOptionValue("time_limit", time_limit)
        h.setOptionValue("mip_rel_gap", 1e-4)
        h.passModel(lp)
        if basis is not None:
            h.setBasis(basis)
        t0 = time.time()
        h.run()
        wall = time.time() - t0
        info = h.getInfo()
        sol = h.getSolution()
        res = {"status": h.modelStatusToString(h.getModelStatus()), "wall": wall,
               "G": -info.objective_function_value, "cols": lp.num_col_, "rows": lp.num_row_, "nnz": self.nnz,
               "nodes": getattr(info, "mip_node_count", 0), "gap": getattr(info, "mip_gap", 0.0),
               "iterations": info.simplex_iteration_count, "x": np.array(sol.col_value),
               "duals": np.array(sol.row_dual) if sol.dual_valid else None, "highs": h}
        return res

    # -- reading a solution

    def starts(self, res, period=0, eps=1e-6):
        out = []
        for i, it in enumerate(self.items):
            v = res["x"][self.y[i, period]]
            if v > eps:
                out.append((it.name, round(v, 3)))
        return out

    def schedule(self, res, eps=1e-6):
        out = []
        for i, it in enumerate(self.items):
            for p in range(self.P):
                v = res["x"][self.y[i, p]]
                if v > eps:
                    out.append((self.t[p], it.name, round(v, 3)))
        return sorted(out)

    def work(self, res, period=0):
        G = list(self.groups.values())
        out = {}
        for (n, li, p), c in self.x.items():
            if p == period and res["x"][c] > 1e-6:
                key = (zad.short(G[n].name), self.layers[li].specific)
                out[key] = out.get(key, 0.0) + res["x"][c]
        return out

    def prices(self, res, period=0):
        if res["duals"] is None:
            return None
        return {k: -res["duals"][self.rows["stock", k, period]] for k in RESOURCES}
