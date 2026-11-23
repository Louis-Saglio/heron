# Heron specification

The models Heron is built on, and the policies that use them. The code
implements this text; where they disagree, the code is wrong.

## Principles

1. **Models predict, policies decide.** A model says what a decision does;
   a policy says what Heron wants. A model has no free constant: its numbers
   come from the game data, the map or the engine source. Every tunable of
   the bot belongs to a policy.
2. **One currency: time.** Every cost and every gain is measured in seconds.
3. **Few models, each general.** A model covers a class of decisions. A new
   kind of decision is first expressed with the existing models.
4. **First order first.** A term enters a model only when it changes a
   decision. What a model neglects is listed with its measured size.

## The common currency

A policy expresses what it wants as a **plan**: an ordered list of things to
obtain (units, buildings, technologies), the order being its priority. The
economic model forecasts when each item of the plan is obtained, at best,
from the current state. The plan's cost is

$$J = \sum_i T_i$$

where $T_i$ is the forecast time at which item $i$ is obtained.

- **Every decision is valued by how much it lowers $J$.** A worker, a
  storehouse, a technology, a house, a barter deal: each is added to the
  plan, the forecast is run again, and $\Delta J$ (in seconds) is its value,
  net of everything it costs — resources, research or build time, the
  building it occupies, the labour of its builders, the delay before its
  effect starts.
- **A resource is worth the time one more unit of it saves on the plan**:
  $\lambda_k = -\partial J / \partial R_k$, in seconds per unit. A resource
  the plan is not waiting for is worth 0. The same holds for a free
  population place and a free production queue.
- The plan comes from a policy; the prices follow from it. Nothing else in
  the bot assigns a value to a resource.

## The schedule is the allocation

The forecast of the plan, with the decisions the models found worth adding
(economy §6), is a schedule: what starts when, with which resources, on
which building, with which workers. Heron executes its head: what the
schedule starts now is ordered now. Resources, population, production
queues and builders are committed in this one place, in plan order, and no
other part of the bot spends.

## Index

| File | Kind | Predicts |
|---|---|---|
| [economy.md](economy.md) | model | gather rates, the forecast of a plan, the prices $\lambda$, the value of every economic decision, the assignment of workers |

Planned, to be submitted before they are written: a combat model (the
outcome and cost of an engagement), and the policies (what to put in the
plan given the strategic situation).

## How a model file is written

1. What it predicts, for which decisions.
2. Its quantities and formulas. Each mechanic cites the engine file it
   comes from, relative to the 0 A.D. repository at tag v0.28.0
   (`binaries/data/mods/public/simulation/...`, abbreviated `sim/...`).
3. What it neglects, and the measured size of each neglected term (or
   "to measure", with the scenario that will measure it).
4. Its validation: the scenarios, what they compare, the accuracy found.

A model file describes the current model only. Rejected alternatives and
their numbers go in commit messages.
