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

A policy expresses what it wants as a **plan**: things to obtain (units,
buildings, technologies), each with a value $v_i$, and a **standing demand**
that absorbs whatever the listed items leave (typically the army the policy
wants to keep producing), so that the plan never ends. The policy also sets
its **time preference** $\tau$, in seconds: how much it discounts what comes
later.

An item of value $v$ obtained at time $T$ is worth $v\,\tau\,e^{-T/\tau}$
seconds. The plan's worth is

$$G = \sum_{\text{items obtained}} v_i\,\tau\,e^{-T_i/\tau}$$

Obtaining an item one second earlier adds $v\,e^{-T/\tau}$ to $G$: one
second, discounted. With every $v_i = 1$ and a long $\tau$, maximising $G$
is minimising $\sum_i T_i$, the sum of the times at which the items are
obtained.

The economic model computes the economy that maximises $G$ from the current
state (economy §4). From it:

- **A resource is worth the time one more unit of it adds to the plan**:
  $\lambda_k(t) = \partial G / \partial R_k(t)$, in seconds per unit, for
  one more unit of $k$ in stock at time $t$. A resource the plan does not
  need is worth 0; a resource needed later is worth less now than one
  needed now. The same holds for a worker's second, a free population
  place, a free production queue and a place to gather.
- **Every economic decision is valued by what it adds to $G$**, net of
  everything it costs: resources, research or build time, the building it
  occupies, the labour of its builders, the delay before its effect
  starts. Workers, houses, dropsites, fields, technologies, production
  buildings and barter are options of the same computation, worth nothing
  in themselves.
- The plan, its values and $\tau$ come from a policy; the prices follow
  from them. Nothing else in the bot assigns a value to a resource.

## The schedule is the allocation

The optimal economy of §4 is a schedule: what starts when, with which
resources, on which building, with which workers. Heron executes its head
(economy §7): what the schedule starts now is ordered now. Resources,
population, production queues and builders are committed in this one
place, and no other part of the bot spends.

## Index

| File | Kind | Predicts |
|---|---|---|
| [economy.md](economy.md) | model | gather rates, the optimal economy for a plan, the prices $\lambda(t)$, the value of every economic decision, the assignment of workers |

Planned, to be submitted before they are written: a combat model (the
outcome and cost of an engagement, from which the time preference $\tau$
and the values of military items will follow), and the policies (what to
put in the plan given the strategic situation).

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
