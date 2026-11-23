# Economy

The economic model computes, for a plan given by a policy, the economy that
obtains it best: how fast resources come in, when each item is obtained,
what each resource is worth at each moment, and what every economic
decision gains or costs, all in seconds. The whole economy is one linear
program over time; its dual values are the prices. The model decides
nothing about what to want: the plan, its values and the time preference
come from a policy (README, "The common currency").

Engine paths are relative to `binaries/data/mods/public/simulation/` at tag
v0.28.0, abbreviated `sim/`. Every number below is read from the game data
at runtime; the values quoted are those of the templates, for the examples.

## 1. Quantities

| Symbol | Meaning | Source |
|---|---|---|
| $k$ | a resource: food, wood, stone, metal | `sim/data/resources/*.json` |
| $g$ | a unit group: the units of one template (same rates, capacity, speed) | |
| $s$ | a supply: a tree, a rock, a mine, a bush, a carcass, a fish, a field | `ResourceSupply` |
| $A_s$, $M_s$, $\rho_s$ | its amount, its maximum number of gatherers, its diminishing-returns ratio (fields) | `ResourceSupply/Max`, `MaxGatherers`, `DiminishingReturns` |
| $\gamma_{g}(s)$ | gather rate of $g$ on the specific type of $s$, units per second | `ResourceGatherer/Rates` × `BaseSpeed`, technologies applied (`sim/components/ResourceGatherer.js`, `RecalculateGatherRates`, `GetTargetGatherRate`) |
| $C_{g,k}$ | carrying capacity | `ResourceGatherer/Capacities` |
| $v_g$ | walk speed, m/s | `UnitMotion/WalkSpeed`, technologies applied |
| $d(s)$ | distance from $s$ to the nearest dropsite accepting its resource, own or, once the diplomacy's `SharedDropsitesTech` is researched, a mutual ally's | `UnitAI.FindNearestDropsite`: obstruction edge distance from the gatherer's position; `sim/components/Diplomacy.js`, `HasSharedDropsites` |
| $R_k$ | stock | |
| $p$, $t_p$, $\Delta_p$ | a period of the time grid, its start, its length | §4 |
| $\tau$, $v_i$ | the policy's time preference and the value of item $i$ | README |

## 2. The gather cycle

A gatherer takes one unit every $1/\gamma$ seconds until it carries
$C$ (`ResourceGatherer.StartGathering`, `PerformGather`, `GATHER_AMOUNT` = 1),
walks to the nearest dropsite, drops, and walks back to the same supply.
Its rate is

$$r_g(s, n) = \frac{C_{g,k}}{C_{g,k} / \big(\gamma_g(s)\,\varphi_s(n)\big) + 2\,d(s) / v_g}$$

where $\varphi_s$ is the engine's diminishing returns
(`ResourceSupply.GetDiminishingReturns`) and $n$ the number of gatherers
registered on $s$: those gathering it and those walking to it (UnitAI
registers a gatherer on its approach, `ResourceSupply.AddGatherer`), not
those carrying a load back (`ResourceGatherer.StopGathering` releases the
place when the load is full):

$$\varphi_s(n) = \frac{1 - \rho_s^{\,n}}{(1-\rho_s)\,n} \quad (n > 1,\ \rho_s \text{ defined}), \qquad \varphi_s(n) = 1 \text{ otherwise.}$$

The total rate of $n$ gatherers on a field is $\gamma (1-\rho^n)/(1-\rho)$ in
the gathering part of the cycle; the $n$-th adds $\gamma\rho^{n-1}$.

Example, female citizen on trees ($\gamma = 0.7$, $C = 10$, $v = 9$):

| $d(s)$ | $r$ (wood/s) | share of the cycle spent cutting |
|---|---|---|
| 5 m | 0.65 | 93 % |
| 10 m | 0.61 | 87 % |
| 20 m | 0.53 | 76 % |
| 40 m | 0.43 | 62 % |
| 80 m | 0.31 | 45 % |

Two consequences the rest of the model uses:

- A technology that multiplies $\gamma$ speeds up only the gathering part:
  ×1.25 on $\gamma$ gives +21 % at 10 m and +14 % at 40 m. Its value depends
  on where the dropsites are, and the model sees it.
- A gatherer that starts on a resource of another kind drops what it
  carries (`ResourceGatherer.StartGathering`): switching costs the load.

## 3. Fronts and layers

A **front** is a dropsite $D$ and a resource $k$, with the supplies of $k$
whose nearest accepting dropsite is $D$: the engine sends every gatherer of
those supplies there. Ranked by $d(s)$, the supplies of a front are cut
into **layers**. A layer $\ell$ has an amount $A_\ell = \sum A_s$, a number
of places $M_\ell = \sum M_s$, and for each group $g$ a rate $r_{g,\ell}$, the
cycle rate at the layer's mean distance. A layer is of one of two kinds:

- **one supply** (a mine, a rock, a field place): its places stay until it
  is exhausted;
- **many small supplies** of similar rates (trees, bushes, carcasses):
  consecutive in distance, whose rates differ by at most a band width.
  Their places disappear with them, which the program takes as places in
  proportion to what is left (§4).

The band width is a computing budget: it bounds the error on any rate by
the band width itself.

- **Depletion** is the amount of each layer running out. Nothing imposes
  an order: the program empties the near layers first because they pay
  more, and moves to the far ones when it must.
- **Fields** are infinite. A field's $M = 5$ places
  (`sim/templates/template_structure_resource_field.xml`) are 5 layers, the
  $j$-th at gather rate $\gamma\rho^{\,j-1}$ ($\rho = 0.9$): the marginal
  gatherer of $\varphi$ (§2).
- **A dropsite** at a candidate site $q$ draws the supplies nearer to $q$
  than to their present dropsite. In the front they belong to, those
  supplies form layers of their own; the dropsite adds, for each of them, a
  twin layer at the new distance. A layer and its twin are the same
  supplies: they share one amount and one set of places (§4).

## 4. The economy as a linear program

**Time grid.** Periods $p = 0 \dots P-1$, short near now and longer further
ahead. The grid is fixed in game time: as time passes, the first period
shrinks, and an elapsed period is dropped and a new one added at the end.
Two successive solves thus have the same structure, and the second starts
from the first's solution (§8). The grid is a computing budget: an item's
time is known to within the length of its period. It reaches $t_P$ with
$e^{-t_P/\tau}$ below the accuracy wanted on $G$: what lies beyond weighs
less than that.

**Items.** The plan's items (README), the standing demand, and the
**options**: every economic means of obtaining them, of value 0 —
a batch of $b$ workers at a building, a house, a dropsite at a site, a
field, a technology, a production building. An item $i$ has a cost vector
$c_i$, a population $\pi_i$ (`Cost`), the building kind it is made at or its
builders, a duration $d_i$, and requirements:

- a batch of $b$ units: $d = t_1\, b^{\beta}\, \mu$, with $t_1$ the unit's
  `Cost/BuildTime`, $\beta$ the building's `Trainer/BatchTimeModifier`
  (0.8 at a civic centre, 1 if absent) and $\mu$ its
  `TrainCostMultiplier/time` (`sim/components/Trainer.js`,
  `GetBatchTime`); its population is reserved when it starts
  (`TryReservePopulationSlots`);
- a technology: `researchTime` × the building's `TechCostMultiplier/time`
  (`sim/components/TechnologyManager.js`);
- a building with a crew of $n$ builders of rate $a$: $d = B / (a\, n^{m})$,
  with $B$ its `Cost/BuildTime` and $m$ the foundation's
  `BuildTimeModifier` (0.7, `sim/templates/special/filter/foundation.xml`;
  `sim/components/Foundation.js`, `CalculateBuildMultiplier`); its crew
  works $n$ worker-seconds per second during $d$. The crew is chosen as in
  §6.

**The present.** What is already under way is part of the program as
fixed items: each batch in a queue and each research with its remaining
time, each foundation with its remaining work and its builders. Their cost
is paid; their effects come when they end.

**Variables** (all $\ge 0$): $x_{g,\ell,p}$ workers of group $g$ on layer
$\ell$ during period $p$; $y_{i,p}$ the number of item $i$ started in period
$p$; $z_{jk,n,p}$ the $n$-th barter deal of the period selling $j$ for $k$;
$e_{T,g,k,p}$ the extra output of technology $T$; $S_{k,p}$ the stock at
$t_p$. Two linear expressions follow:

- $Y_i(p) = \sum_{p' :\, t_{p'} + d_i \le t_p} y_{i,p'}$, the number of $i$
  done by $t_p$;
- $o_{i,p',p}$, the length of $[t_{p'}, t_{p'} + d_i)$ inside period $p$: the
  time an item started in $p'$ spends in period $p$.

**Constraints**, for every period:

| | |
|---|---|
| stock | $S_{k,p+1} = S_{k,p} + \Delta_p\big(\sum_{g,\ell \in k} r_{g,\ell}\, x_{g,\ell,p} + \theta_k\big) + \sum_{g,T} e_{T,g,k,p}\,\Delta_p + \text{barter} - \sum_i c_{i,k}\, y_{i,p}$, $S_{k,0} = R_k$; $\theta_k$ the trickle (`ResourceTrickle`) |
| labour | $\Delta_p \sum_\ell x_{g,\ell,p} + \sum_{i \text{ built by } g} n_i \sum_{p' \le p} o_{i,p',p}\, y_{i,p'} \le \Delta_p \big(N_g + \sum_{i \text{ trains } g} b_i\, Y_i(p)\big)$ |
| places | $\sum_g (x_{g,\ell,p} + x_{g,\ell',p}) \le M_\ell$ for a layer of one supply and its twin $\ell'$; $\le M_\ell\,(1 - Q_\ell(p)/A_\ell)$ for a layer of small supplies, $Q_\ell(p)$ the amount taken from it and its twin before $t_p$; a twin's places are also bounded by $M_\ell\, Y_D(p)$, those of a field place by $Y_F(p)$ |
| amounts | $Q_\ell(P) \le A_\ell$, with $Q_\ell(p) = \sum_{p' < p} \Delta_{p'} \sum_g (r_{g,\ell}\, x_{g,\ell,p'} + r_{g,\ell'}\, x_{g,\ell',p'})$ |
| queues | $\sum_{i \text{ made at } q} \sum_{p' \le p} o_{i,p',p}\, y_{i,p'} \le \Delta_p\,\big(n_q + \sum_{i \text{ builds } q} Y_i(p)\big)$ for each building kind $q$ |
| population | $\text{pop} + \sum_i \pi_i \sum_{p' \le p} y_{i,p'} \le \text{cap} + \sum_{h} \text{bonus}_h\, Y_h(p)$ |
| unlocks | an item that requires $r$ (a phase, a technology, a building) starts only once $r$ is done: $y_{i,p} = 0$ for $t_p < t^{\text{done}}_r$ (below) |
| technologies | $e_{T,g,k,p} \le \sum_{\ell \in k} (r'_{g,\ell} - r_{g,\ell})\, x_{g,\ell,p}$ and $e_{T,g,k,p} \le \bar e_{T,g,k}\, Y_T(p)$: $r'$ the rate with $T$ (its `modifications` on $\gamma$, $C$ or $v$, through §2), $\bar e$ its extra output with every worker of $g$ on the best layers of $k$ |
| barter | the deals of a period are bounded by $Y_{\text{market}}(p)$ (none before a market) and priced in §5 |
| plan | $\sum_p y_{i,p} \le 1$ for a listed item (or the count wanted); the standing demand is bounded by the population cap over its population |

**Unlocks are whole.** A phase, or any item that others require, is
obtained entirely or not at all: a fraction of a phase unlocks nothing.
Each unlock $r$ has a completion period, an integer, and the program is
solved by branch and bound over these integers (a few unlocks over the
grid), each node a linear program. Every other variable is continuous.

**Objective.** Maximise the plan's worth

$$G = \sum_i v_i \sum_p y_{i,p}\, \tau\, e^{-(t_p + d_i)/\tau}$$

(options have $v_i = 0$; the standing demand has a value per unit).

**What this gives.**

- For given unlocks, a linear program, solved to its optimum. Its optimal
  value $G^*$ is non-decreasing in the stock, the amounts, the places and
  the workforce, concave in them, and continuous: one more resource never
  makes the plan worse.
- Its solution, though, is not continuous: a degenerate program can jump
  between optimal vertices, and its duals are then not unique. Stability
  therefore comes from three properties of how the program is used, not
  from $G^*$:
  1. the solve starts from the previous solution and the simplex moves
     only to a strictly better one: while the previous schedule stays
     optimal, it is kept (the fixed grid makes this possible);
  2. what is started is committed: it enters the next solves as part of
     the present, its cost paid;
  3. what can be undone at a cost — a worker's place — is moved only when
     the gain exceeds that cost (§7).
  A choice that flips between two solves is a choice between options of
  almost equal value: the flip costs at most their difference.
- The solution is a schedule: what starts in each period, with which
  workers on which layers. Its first period is what to do now (§7).

## 5. Prices

The dual values of the program are the prices of everything scarce:

| Dual of | Price | Meaning |
|---|---|---|
| stock of $k$ at $p$ | $\lambda_k(p)$, s per unit | what one more unit of $k$ at $t_p$ adds to $G$ |
| labour of $g$ at $p$ | $w_g(p)$, s per worker-second | what one second of a worker's time is worth: the cost of taking it off work to build, walk or fight |
| places of $\ell$ at $p$ | rent of $\ell$ | what a place on $\ell$ is worth beyond the worst place in use: the value of being near a dropsite |
| queues of $q$ at $p$ | $\kappa_q(p)$ | what a free second of a production queue is worth |
| population at $p$ | $\lambda_{\text{pop}}(p)$ | what a free population place is worth |

They are the duals of the final node of the branch and bound, the unlocks
fixed, from the basis the simplex ends on: deterministic, and unchanged
while the schedule is.

- A price is 0 when its constraint has slack: a stock nobody needs is
  worth nothing, a queue that idles is worth nothing. When every resource
  price is 0, the plan is limited by queues or population, and $\kappa$ or
  $\lambda_{\text{pop}}$ says which.
- With one item waiting, identical workers and a long $\tau$,
  $\lambda_k = 1/(N\, r_k)$ with $r_k$ the marginal rate on $k$: a resource
  is worth the labour its last unit costs.

Example: 20 women must gather 500 food and 300 wood for one item ($v = 1$,
long $\tau$), at 0.4 food/s on fields and 0.61 wood/s. The optimum puts
14.4 on food and 5.6 on wood; the item is obtained after
$(500/0.4 + 300/0.61)/20 = 87$ s. One food is worth
$1/(20 \times 0.4) = 0.125$ s, one wood $0.082$ s: food is worth 1.52 wood
because it is slower to gather.

**The market** (`sim/components/Barter.js`). Selling 100 of $j$ gives
$100\, e_{jk}$ of $k$, with

$$e_{jk} = \frac{100 - 10 + \delta_j}{100 + 10 + \delta_k}$$

(the `truePrice` of every resource is 100; the player's `BarterMultiplier`
is 1 unless a civ or a technology changes it). Each deal lowers the price
difference $\delta_j$ of the sold resource and raises $\delta_k$ by
$2 \times$ the amount bought $/100 = 2\,e_{jk}$ (`ExchangeResources`), and
every $\delta$ returns toward 0 by 0.5 every 5 s (`ProgressTimeout`). The
$\delta$ are **shared by all players**: `Barter` is a system component, so
every player's deals move everyone's prices. The program prices the deals
of a period from the present $\delta$, after their return since now: the
$n$-th deal of a pair at the $\delta$ the earlier ones leave, a concave,
piecewise-linear exchange. A deal adds $100\,(e_{jk}\lambda_k - \lambda_j)$ to
$G$; at the optimum no deal left out has a positive value, so
$\lambda_k / \lambda_j \le 1/e_{jk}$ for every pair: the market bounds the
prices, it does not set them. At equal prices $e = 0.82$.

## 6. Decisions

Every economic decision is a variable of the program, and its value is
what it adds to $G$. The candidates are generated — the technologies
available, the batch sizes, a house, a field, the production buildings,
and dropsite sites at the legal positions next to the layers with the
highest rent — and enter the program by **column generation**:

- A candidate that is a single column (a batch, a house, a production
  building) is priced by its reduced cost: what one unit of it brings at
  the current duals (its effects on stock, labour, queues, population)
  minus what it costs at the same duals.
- A candidate that brings rows of its own (a dropsite and its twin layers,
  a field and its places, a technology and its extra outputs) is priced by
  its **pricing problem**: the best use of its new rows at the current
  duals of the existing ones, for a dropsite
  $\sum_p \Delta_p \sum_{\ell'} \text{places} \times \max\big(0,\ r_{g,\ell'}\lambda_k(p) - w_g(p) - \text{rent of its layer } \ell\big)$
  over the best group, less its cost, its crew's labour and its build time
  at the same duals. By duality this is an upper bound on what the
  candidate can add to $G$: a candidate whose bound is not positive cannot
  improve the plan and is left out.
- Candidates with a positive reduced cost or bound enter the program,
  which is solved again; when none is left, the solution is optimal over
  all the candidates.

How many sites are generated is a computing budget: it changes which
options are seen, never what an option is worth.

**Example: two technologies** (long $\tau$). A gives +1.2 wood/s to the
woodcutters for 100 metal and 120 s of research, B the same for 200 metal
and 10 s. With metal at 2 and wood at 1.64 worker-seconds per unit, B
yields $1.2 \times 110 \times 1.64 = 216$ more and costs
$100 \times 2 = 200$ more: B is slightly better. If the plan needs no
metal, $\lambda_{\text{metal}} = 0$ and B is clearly better. If A is
researched at the civic centre, its 120 s are paid at $\kappa$ of that
queue, the training of workers it delays.

**Builders.** A building of build time $B$ that adds $b$ to $G$ per second
once done (its rents and queue or population prices), built by $n$ workers
of labour price $w$, costs $w B n^{1-m}$ of labour and $b B n^{-m}$ of
waiting. The best crew is

$$n^* = \frac{m}{1-m}\,\frac{b}{w} = \frac{7}{3}\,\frac{b}{w} \quad (m = 0.7)$$

computed from the duals of the previous solution. A storehouse that brings
10 woodcutters from 40 m to 10 m gives each $0.61 - 0.43 = 0.18$ wood/s
more: $b/w = 10 \times 0.18 / 0.43 = 4.2$, so $n^* \approx 10$: the
woodcutters build it themselves, in 8 s instead of 40.

## 7. Execution and assignment

**What starts now.** The first period of the solution says what to start.
A whole item the program starts in part (0.4 of a storehouse) is decided by
solving twice, with that item started now and with it not started in the
first period, and keeping the better; the same for the fractional part of
a number of batches. This is exact for that choice. An item starts when the
schedule says so and the engine allows it (stock, queue, population): the
schedule is the only place resources are committed (README). Once
started, it is part of the present (§4).

**Who goes where.** The program says how many workers of each group work
each layer now. The assignment gives each worker a supply so as to
maximise

$$\sum_u r_u(s_u) \int_{t_{\text{walk}}(u, s_u)}^{W(s_u)} \lambda_{k(s_u)}(t)\, dt$$

with those numbers per layer and $M_s$ places per supply, where
$t_{\text{walk}}$ is the unit's walk to the supply and $W(s)$ the end of the
time the program keeps working its layer. It is a transport problem,
solved exactly. A busy worker is moved only when the gain exceeds what
moving costs: its walk (in the integral) and the load it drops when it
changes resource ($\lambda_k$ now times what it carries). A worker walking
back loaded is moved once it has dropped its load, which costs nothing.
These costs come from the model; no threshold keeps the assignment stable.

## 8. Computation

**Size**, for 20 periods, 3 groups, 30 layers with their twins, 30
candidate items, 12 barter pairs of 3 deals and 4 technologies on one
resource each:

| | Variables | Rows |
|---|---|---|
| work $x$ | 3 × 30 × 20 = 1 800 | places 30 × 20 = 600, amounts 30 |
| items $y$ | 30 × 20 = 600 | queues 5 × 20 = 100, population 20 |
| barter $z$ | 12 × 3 × 20 = 720 | |
| technologies $e$ | 4 × 3 × 20 = 240 | 2 × 240 = 480 |
| stock $S$, labour | 4 × 20 = 80 | stock 80, labour 60 |
| total | about 3 400 | about 1 400 |

A column of $x$ has about five non-zeros (stock, labour, places, amounts,
technology): the matrix is very sparse, and dense storage (about 5 million
entries) is out of the question. The solver is a sparse revised simplex,
warm-started from the previous basis, run again when the state has changed
(an item done, a layer exhausted, a unit gained or lost, a candidate priced
positive) and otherwise when the first period ends. Between two solves,
the schedule is executed as it is.

**Before the bot.** The program is first built and solved outside the
engine (`tools/`, with an existing solver) on states dumped from real
games, to measure what this specification can only estimate: its real
size, the time per solve, the integrality gap, and how much the solution
moves between successive solves. The solver in the bot is written after.

The time per solve is kept within the decision budget (AGENTS.md,
Performance). When it is exceeded, the grid, the layer bands and the site
candidates are coarsened, which degrades the model only by the bounds
stated in §3, §4 and §6.

## 9. Scope

Covered: trees, rocks, mines, bushes, fields, carcasses, fish (ships and
docks are groups and dropsites like the others), treasures (a supply
collected on arrival: its value is $\lambda_k A_s$ against the walk),
resource trickles, barter, allied dropsites once shared.

Not yet covered, each to be submitted before it is added: hunting (kill
and chase time before the carcass), corrals, trade between markets,
tribute, loot, and the risk of a site near the enemy (a policy decides
which sites are allowed).

## 10. Neglected

| Term | Size |
|---|---|
| The walk is a straight line; the path goes around obstructions | to measure (`cycle`) |
| Time between a load and the next state of the unit (engine turns) | to measure (`cycle`) |
| Congestion around a dropsite | to measure (`crowd`) |
| Items other than unlocks are fractional beyond the first period: large purchases far ahead, and today's prices, are optimistic | to measure: integrality gap against an integer solve (prototype, `plan`) |
| An item's time is rounded to its period | at most the period's length |
| A layer's rate is its mean distance's | at most the band width (§3) |
| The places of small supplies disappear in proportion to what is left, not supply by supply | to measure (`front`) |
| Field places as marginal gatherers, with the walk | exact at $d = 0$; to measure (`crowd`) |
| The walk of workers moving between layers inside the program (the assignment prices it, §7) | to measure (`plan`) |
| Technologies on the same rate add their gains instead of compounding | to measure on the gather technologies |
| Other players' future deals at the market | to measure in games with markets |
| After a supply is exhausted the engine picks the next one itself, until the next decision | to measure (`front`) |
| What lies beyond the grid | at most $e^{-t_P/\tau}$ of $G$ |

## 11. Validation

Each scenario sets up the situation in the engine and compares the
measured quantity with the model's prediction.

| Scenario | Measures | Against |
|---|---|---|
| `cycle` | one gatherer per unit group and supply type, $d$ from 2 to 100 m | $r_g(s, 1)$ |
| `crowd` | $n$ gatherers on one field, one mine, one tree cluster; $n$ builders on one building | $\varphi_s(n)$; $B / n^m$ |
| `front` | a woodline and a patch of bushes with a dropsite, 5 to 40 gatherers, until exhaustion | the stock over time predicted by the program |
| `train` | batches of 1 to 10 at each kind of building | $t_1 b^\beta \mu$ |
| `barter` | a sequence of deals with pauses | $e_{jk}$ and $\delta(t)$ |
| `plan` | a fixed plan from the start of a game against an idle player, on several maps, through a phase change | the times of the program, $G$ against the integer optimum on short plans, the time per solve, the movement of the schedule between solves |

The economy as a whole is measured on `plan`: the bot's $G$ against the
program's optimum for the same start, and against Louis's play of the same
plan on the same maps.
