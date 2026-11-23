# AGENTS.md — Heron

Heron is an in-engine JavaScript AI for 0 A.D., shipped as a 0 A.D. mod and
developed against **0.28.0 only**. Petra is the reference implementation of
the engine's AI interface.

It is named after Heron of Alexandria, who built programmable automata and
showed that light reflected by a mirror takes the shortest path: a machine
that acts, and the first known principle of a shortest path.

## The goal

Heron plays **every civilisation, on every map and every biome**, in 1v1 and
in team games, **under every reasonable game setting** — every victory
condition, map size, population cap, starting resources, map visibility,
ceasefire, player count (degenerate combinations, such as eight players on a
tiny map or a population cap of 50, are out of scope) — and wins: it beats
Petra Very Hard clearly and consistently, it beats Brennus and Strategos. It
wins by playing well — sound economy, timing, army composition, positioning,
use of each civ's own units, buildings, technologies and bonuses — not by
exploiting the blind spots of a particular opponent AI: everything it does
must still make sense against a strong human player.

**Only this goal matters.** Intermediate step goals are means to it: set them,
measure against them, revise or drop them when the results say so. Step goals
are tracked as GitHub milestones and issues, never in a file.

## The design: models predict, policies decide

Heron is built on a small number of mathematical models of the game, and on
policies that use them. This separation is the project; everything else
follows from it.

- **A model predicts.** Given the state (map, units, buildings, resources,
  technologies) and a candidate decision, it says what the decision does:
  what it costs, how long it takes, what it blocks, when its effect starts
  and what it yields afterwards. A model has **no free constant**: every
  number in it comes from the game data (templates, technologies), the map,
  or the engine's mechanics as the source code implements them. A tunable
  number inside a model is a defect.
- **A policy decides.** It states what Heron wants given the strategic
  situation (what to buy, by when, what risk it accepts), asks the models
  what each option does, and chooses. Every tunable of the bot lives in a
  policy, under a name that says what it means, and there are few of them.
- **One currency: time.** Every cost and every gain is measured in time.
  Resources have no fixed value: a resource is worth the time one more unit
  of it would save on what the policy wants to buy (its price follows from
  the plan and the gather rates; a resource the plan does not need is worth
  nothing). Research and build times, the occupation of a building, the
  walk of a unit to its work are costs in the same unit. Decisions are
  compared in that unit only.

### What a good model is

- **General.** A model covers a class of decisions, not a case. The economic
  model answers for every assignment, dropsite, field, technology, unit
  trained and barter alike; a combat model answers for every engagement.
  When a new kind of decision appears, it is expressed with the existing
  models first. A new model, or a model for one case, is a design change
  and needs Louis's approval.
- **Simple.** First-order terms first. A term is added only when it is shown
  to change a decision — not when it only makes a prediction more precise.
  The simplest model that takes the right decisions is the right model.
- **Derived, not fitted.** A model is derived from the rules of the game (the
  0 A.D. source), never fitted to the bot's own games. When a prediction
  disagrees with the engine, the cause is found in the engine's mechanics
  and written into the model; adding a correction factor is not a fix.
- **Checked against the engine.** Every model has scenarios that measure,
  in the engine, what it predicts, and a stated accuracy. A model is
  trusted only within what its scenarios cover.
- **Optimal where it can be.** A model that chooses (an assignment, a
  schedule) computes the optimum of the problem it states, or says how far
  from it its answer can be.

### Failures

A behaviour that goes wrong in a game is one of three things, and the fix
goes where the cause is:

1. the **model** predicts wrongly (prediction against what happened): fix
   the model, in the specification first;
2. the **policy** wants the wrong thing given correct predictions: fix the
   policy;
3. the **code** does not do what the specification says: fix the code.

It is never a reason to add a rule beside the models for that case.

## The specification

`spec/` holds the models and the policies in mathematical form. It is the
most valuable part of the repository: the code implements it, and code that
disagrees with it is a bug.

- **Specification first.** A change of behaviour starts as a change of the
  specification; the code follows in the same commit or the next.
- One file per model (`spec/economy.md`, ...) and one per policy, plus
  `spec/README.md`: the principles, the common currency, the index. Each
  model file has: what it predicts, its formulas with the engine source
  path of every mechanic they use (`binaries/data/mods/public/...` at tag
  v0.28.0), what it neglects and the measured size of what it neglects, and
  its validation (scenario, accuracy).
- The specification describes **the current** models, and only them. It is
  kept true: when a model changes, its text changes. Alternatives that were
  tried and rejected, and why, go in commit messages, not in the
  specification.
- Specification changes to a model's scope, a new model or a new policy are
  submitted to Louis before they are implemented.

## Layout

- `spec/` — the models and policies (see above).
- `bot/` — the mod: `mod.json` + `simulation/ai/heron/`.
- `scenarios/` — a separate mod of scenario maps and trigger scripts that
  measure one model or one behaviour in isolation; mounted only by the
  harness. They are the tests of the project.
- `tools/` — development tooling: match runner, harness, analysers, visual
  replay, game data loader (see `tools/README.md`).

## Hard constraints

- **Determinism**: same seed → identical game. The bot never uses unseeded
  randomness; game settings that resolve randomly (biome, player placement,
  civs) are pinned on the command line.
- **Every game setting is explicit.** No match runs on an implicit default:
  the runner sets every setting, checks after the match that the engine
  applied it, and records it with the match.
- **The 0 A.D. source reference** is a checkout of the official repository
  (https://gitea.wildfiregames.com/0ad/0ad) at tag `v0.28.0`, at `~/Work/0ad`
  on boobynator. Its text files are identical to the installed game data.
  Trust it over general 0 A.D. knowledge, and over any document.
- **The game stays stock.** Heron plays the unmodified 0.28.0 game: never
  change gameplay, in the engine or in the public mod; the bot mod contains
  only the AI. Tooling may go further — harness and scenario mods, engine
  patches for instrumentation, profiling or faster headless runs — provided
  a patched engine is built separately and its games reproduce the stock
  binary's games bit for bit on the same seeds before any result is used.
- **Original work.** The bot is written from the specification. Do not copy
  code from Petra, Brennus or Strategos, and do not port Strategos
  subsystems: reading them to understand the AI interface or an opponent is
  fine. Tooling may be taken from Strategos (`~/Work/strategos/tools`,
  `scenarios/`), adapted and documented here.
- **Decision cadence**: the bot decides on one turn out of 8, staggered by
  player id like Petra (`simulation/ai/petra/_petrabot.js`,
  `(turn + player) % 8 == 5`).
- **Performance**: the bot must not slow the simulation. No full-map or
  full-entity scans per decision; cached entity collections, the shared maps
  of the AI interface, incremental updates. A model whose exact computation
  is too costly states the approximation it uses and its bound. Measure the
  time per decision turn and keep it bounded.

## Code

- **The code mirrors the specification**: one module per model and per
  policy, named as in `spec/`, with the specification's names for its
  quantities.
- **No comments, except references to the specification** (`// spec
  economy §3`). Names, structure and data carry the meaning; the reasoning
  lives in `spec/` and in commit messages.
- **Numbers**: a number written in a model's code is a game mechanic the
  specification cites (and preferably read from the game data at runtime);
  a number written in a policy is a named tunable listed in the policy's
  specification. Anything else is a defect.
- **No unit tests.** The test is the engine: scenarios for the models,
  matches for the policies.

## Architecture

- **Layers, one direction**: world model (built once per decision turn,
  read-only) → models (pure functions of the world and a candidate
  decision) → policies (choose) → executor (engine commands).
- **Models never decide and never hold strategy; policies never compute
  what a model computes.** A policy that needs a prediction no model gives
  is a gap in the models, raised as such.
- **Everything scarce is decided in one place**: resources, population,
  production slots and workers are committed by a single decision step
  that compares options in the common currency. No subsystem spends on its
  own, and no value is written by hand to rank one kind of spending against
  another.
- **Generic first, specific where it pays.** Units, costs, rates,
  production sites and technologies are read from the templates at
  runtime. Play that only works in a given context (a civ's own units or
  bonuses, a victory condition, a map type) is a named policy selected from
  the observed context, never a check scattered through the code.
- **Stable decisions.** A small change of the state causes a small change of
  behaviour: decisions compare options by their predicted value with
  explicit commitment (a decision taken is kept until a better option gains
  more than the cost of switching, which the models price). Chaotic
  sensitivity is a defect.

## Telemetry

- **Every decision is logged with its prediction**: the options compared,
  their predicted cost and gain in time, the one chosen. The bot measures
  what the decision actually yielded and logs the error. Prediction against
  realisation is the main window on the bot: a growing error points to the
  model, a correct prediction with a bad outcome to the policy.
- `print()` goes to stdout: tagged lines, coarse and rate-limited. Logging
  costs simulation time: measure the turn rate with and without it when in
  doubt.

## Evaluating

- **Models**: on their scenarios, prediction against the engine, with the
  accuracy the specification states.
- **Economy**: against an idle opponent first, as a fraction of the optimum
  the model computes for the same map and start, and against Louis's own
  play on the same setups (the human reference). Gains relative to the
  previous commit are not enough: the distance to what is possible is what
  matters.
- **The whole bot**: matches against Petra (Very Hard = difficulty 5, which
  also gathers 56 % faster; every behaviour), Brennus (`~/Work/brennus` at a
  pinned commit), Strategos (`~/Work/strategos` at a pinned commit) and
  Heron's previous versions; paired on the same seeds, judged first on the
  metric the change targets, then on results. Rotate seeds, civs, maps,
  biomes and settings; never tune on one configuration. A win that relies
  on an opponent's blind spot does not count.

## Running games

- **Headless**, one isolated HOME per match, settings pinned, under
  `nice`/`ionice`. Batches run as background jobs with a completion
  notification — never polled. Syntax-check the mod before a batch.
- **Use all available CPU**: boobynator (16 threads), the thinkpad (`ssh
  thinkpad`, 8 threads, when it is on and on mains power), vps2 (`ssh vps2`,
  4 cores, shared with its services). A host joins a batch only once its
  games are verified bit-identical to boobynator's on the same seeds.
- **Every game has a limit set before it starts** (in-game time and wall
  clock), the shortest that answers the question; lengthen it only on
  measured evidence that the extra minutes change the answer. A game that
  hits the wall-clock cap is a defect to investigate.
- **A game is launched only for information the games already played do
  not give.** Before a batch, state the question and why that many games
  are needed. Start small, then decide. A model question is answered by a
  scenario, not by matches.
- **Visual**: when telemetry is not enough, replay the recorded game in the
  GUI. Louis can also play against the installed bot.

## Sharing progress

- Commit and push to `main` at each significant step, one concern per
  commit. Commit messages carry what changed, why, and the measurement that
  justified it (command, seeds, numbers).
- After each bot commit, install the mod into the local 0 A.D. so Louis can
  play against it.
- **Never edit `AGENTS.md`**: it is owned by Louis. If something in it seems
  wrong, report it to him.
