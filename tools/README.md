# tools/

Development tooling for Heron. Not part of the bot. `run.py`, `analyze.py`,
`check_bot.py`, `hosts.json` and `harness/` come from Strategos
(`~/Work/strategos/tools` at 6f8f24d), adapted to Heron; their help texts
still mention a few Strategos tools not brought over (`identity.py`,
`gather.py`...).

| Tool | What it does |
|---|---|
| `run.sh` (`run.py`) | run batches of headless matches on every available host (`run.sh -h`); AIs: `heron` (this repo's `bot/`, or `-m heron=DIR`), `petra`, `brennus` and `strategos` (`~/Work/...@HEAD`, or `-m NAME=GIT_DIR@REV`) |
| `harness/` | the `heron-harness` mod mounted in every match: game settings, statistics, map snapshots, standings, gather census, resignation, time limit |
| `hosts.json` | match hosts: ssh name, slot count, determinism verification, calibration |
| `analyze.py` | one-line-per-match summary of a batch |
| `check_bot.py` | bot code rules: every JS file parses; no comment except a reference to an existing section of the specification, `// spec FILE §N` |
| `telemetry.py` | read the bot's tagged lines from a match's `stdout.log`, joining the parts of values too long for the engine's print buffer; `--summary` for STATE |

## The STATE line

At its first decision the bot prints `[STATE]`: everything the economic
model starts from (spec/economy.md). Fields: `time` (ms), `civ`, `mapSize`
(m), `stock`, `population`, `populationLimit`, `populationMax`,
`researched`, `barterPrices`; `units` and `structures` of the player (id,
template, owner, x, z, angle, obstruction `shape` as `{w, d}` or `{r}`,
classes; units add gather `rates`, `capacities`, walk `speed`, `build`
rate, `carrying`, UnitAI `state` and order `target`; structures add
`dropsite` types, `foundation` progress, production `queue`,
`population` bonus); `supplies`, every entity with a resource supply the AI
sees, any owner (`type` generic.specific, `amount` and `max`, the string `"Infinity"` for
an infinite supply such as a field, `places` =
MaxGatherers, `gatherers`, `diminishing`); `territory` (owner per cell,
mask 0x1F) and `passability` (the `default-terrain-only` class bits), as
`{width, height, cellSize, runs}` with `runs` = value, count, value,
count... row by row.

The engine's `print` drops any text longer than its 16384-byte buffer
(`debug_printf`, `source/lib/debug.cpp`): the bot splits a long value into
`[TAG P i/n]` parts, which `telemetry.py` joins.
