# Economy

The economic model predicts how fast resources come in, when the items of a
plan are obtained, what each resource is worth, and what every economic
decision gains or costs, all in seconds. It decides nothing: the plan comes
from a policy, and the decisions it values are taken by the schedule
(README, "The schedule is the allocation").

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
| $d(s)$ | distance from $s$ to the nearest own dropsite accepting its resource | `UnitAI.FindNearestDropsite`: obstruction edge distance from the gatherer's position |
| $R_k$ | stock | |

## 2. The gather cycle

A gatherer takes one unit every $1/\gamma$ seconds until it carries
$C$ (`ResourceGatherer.StartGathering`, `PerformGather`, `GATHER_AMOUNT` = 1),
walks to the nearest dropsite, drops, and walks back to the same supply.
Its rate is

$$r_g(s, n) = \frac{C_{g,k}}{C_{g,k} / \big(\gamma_g(s)\,\varphi_s(n)\big) + 2\,d(s) / v_g}$$

where $n$ is the number of gatherers on $s$ and $\varphi_s$ the engine's
diminishing returns (`ResourceSupply.GetDiminishingReturns`):

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

## 3. Fronts and supply curves

A **front** $f$ is a dropsite $D$ and a resource $k$, with the supplies of $k$
whose nearest accepting dropsite is $D$ (the engine sends every gatherer of
those supplies there). Each supply offers $M_s$ places. Ranked by the rate
they give, the places of a front form a decreasing sequence of marginal
rates, so the front's flow $F_f(n)$ for $n$ gatherers is concave. Merging
the fronts of a resource gives its **supply curve** $F_k(n)$: the flow of
$n$ gatherers placed on the best places.

**Depletion.** A front is used from the dropsite outward. Its supplies,
ranked by $d(s)$, give the distance at which the front stands after an
amount $Q$ has been taken from it:

$$d_f(Q) = d(s_j) \quad\text{for the first } j \text{ with } \sum_{i \le j} A_{s_i} > Q$$

so that the front's rate falls as it is worked, $dQ/dt = F_f(n, d_f(Q))$, and
a front is exhausted when $Q$ reaches its total amount. Fields have
$A_s = \infty$ and do not move.

**A new dropsite** at $p$ moves to it every supply nearer to $p$ than to its
present dropsite, with its new $d(s)$; the fronts are rebuilt. This is the
whole effect of a dropsite.

## 4. The forecast of a plan

A **plan** $P = (p_1, \dots, p_m)$ is an ordered list of items. An item is a
unit batch, a building, a technology or a barter deal, with:

- its cost vector $c_i$ and population $\pi_i$ (`Cost`);
- where it is made and for how long:
  - a batch of $b$ units in a building:
    $t = t_1\, b^{\beta}\, \mu$, with $t_1$ the unit's `Cost/BuildTime`, $\beta$
    the building's `Trainer/BatchTimeModifier` (0.8 at a civic centre, 1 if
    absent) and $\mu$ its `TrainCostMultiplier/time`
    (`sim/components/Trainer.js`, `GetBatchTime`);
  - a technology: `researchTime` × the building's `TechCostMultiplier/time`
    (`sim/components/TechnologyManager.js`);
  - a building with $n$ builders of rate $a$:
    $t = B / (a\, n^{m})$, with $B$ its `Cost/BuildTime` and $m$ the
    foundation's `BuildTimeModifier` (0.7, `sim/templates/special/filter/foundation.xml`;
    `sim/components/Foundation.js`, `CalculateBuildMultiplier`), plus the
    builders' walk to the site;
- its effect when done: units added (after their walk to their work),
  a building added (fronts, population capacity, a new production queue),
  a modification applied ($\gamma$, $C$, $v$...).

The forecast plays the plan forward as a continuous flow of labour, from
event to event (an item starts or ends, a front is exhausted):

1. **Items start in plan order of priority.** An item starts as soon as the
   stock, less the cost of every earlier item not yet started, covers its
   cost, its building or builders are free, and the population has room. A
   later item may start first only if it delays no earlier one.
2. **Labour goes to the earliest items.** Between two events, the workers
   are split between resources to cover, as early as possible, the deficit
   of the first item still short of resources, then of the next. With
   concave supply curves and a few unit groups this is a small linear
   program (groups × resources, over the places of the fronts), solved
   exactly at each event.
3. **Done items change the state** for the rest of the forecast.

The forecast gives the time $T_i$ each item is obtained, the schedule (what
starts when, with which workers), and $J = \sum_i T_i$. With the plan order
fixed, rule 2 is optimal: each item is obtained as early as the earlier
ones allow.

## 5. Prices

$$\lambda_k = -\frac{\partial J}{\partial R_k} \ \ \text{(s per unit)}, \qquad \lambda_{\text{pop}},\ \lambda_{\text{queue}} \text{ likewise for a free population place and a free production queue.}$$

They are the dual values of the linear programs of §4, summed over the
segments of the forecast (or, to check them, the difference of two
forecasts with one load more of $k$).

- $\lambda_k = 0$ when no item waits for $k$. A stock nobody needs is worth
  nothing, and when every price is 0 the plan is limited by queues or
  population, not by gathering: $\lambda_{\text{queue}}$ or
  $\lambda_{\text{pop}}$ says which.
- With one item waiting and identical workers,
  $\lambda_k = 1 / (N\, r_k)$, with $r_k$ the marginal rate on $k$: a
  resource is worth the labour its last unit costs.

Example: 20 women must gather 500 food and 300 wood for one item, at
0.4 food/s on fields and 0.61 wood/s. The optimum puts 14.4 on food and
5.6 on wood, and the item is obtained after
$(500/0.4 + 300/0.61)/20 = 87$ s. One food is worth
$1/(20 \times 0.4) = 0.125$ s, one wood $0.082$ s: food is worth 1.52 wood
because it is slower to gather.

**The value of a worker's time.** A unit of group $g$ working at $s$ saves
$\lambda_k\, r_g(s)$ seconds of plan per second. Its best value
$w_g = \max_s \lambda_{k(s)}\, r_g(s)$ is what a second of its labour is
worth: the cost of taking it off work to build, walk or fight.

**The market** turns resources into one another
(`sim/components/Barter.js`). Selling 100 of $j$ gives
$100\, e_{jk}$ of $k$, with

$$e_{jk} = \frac{100 - 10 + \delta_j}{100 + 10 + \delta_k}$$

(the `truePrice` of every resource is 100, the player's `BarterMultiplier`
is 1 unless a civ or a technology changes it). Each deal moves the price
difference $\delta$ of the sold resource down and of the bought one up by
$2\,e_{jk}$, and every $\delta$ returns toward 0 by 0.5 every 5 s. A deal is
worth $100\,(e_{jk}\lambda_k - \lambda_j)$ seconds; at equal prices
$e = 0.82$. Once a market exists, no deal is worth making exactly when
$\lambda_k / \lambda_j \le 1 / e_{jk}$ for every pair: the market bounds the
prices, it does not set them.

## 6. The value of a decision

Every economic decision $X$ is valued the same way: it is added to the plan
where it would be made (as soon as possible, unless stated), the forecast
is run again, and

$$\Delta J(X) = J(P) - J(P \oplus X)$$

is its value in seconds, net of all its costs. $X$ is worth making when
$\Delta J(X) > 0$.

| Decision | What it changes in the forecast |
|---|---|
| train a unit, a batch of $b$ | a worker more after its training and walk; the batch time $t_1 b^\beta$ |
| a dropsite at $p$ | the fronts (§3) |
| a field at $p$ | a supply with $A=\infty$, $M = 5$, $\rho = 0.9$ (`sim/templates/template_structure_resource_field.xml`) |
| a house | population capacity |
| a technology | $\gamma$, $C$, $v$ or costs, from its `modifications` |
| a production building | a queue |
| $n$ builders on a building | its build time and their lost labour |
| a barter deal | the stock, at $e_{jk}$ |

**Example: two technologies.** A gives +1.2 wood/s to the woodcutters for
100 metal and 120 s of research, B the same for 200 metal and 10 s. With
metal at 2 and wood at 1.64 worker-seconds per unit ($N\lambda$, the
labour the last unit costs), B yields $1.2 \times 110 \times 1.64 = 216$ more and costs
$100 \times 2 = 200$ more: B is slightly better, whatever the horizon. If
the plan waits for no metal, $\lambda_{\text{metal}} = 0$ and B is clearly
better. If A is researched at the civic centre, its 120 s also stop the
training of workers, and the forecast counts it.

**Example: builders.** A building of build time $B$ that brings $b$ seconds
of plan per second once done, built by $n$ workers each worth $w$, costs
$w B n^{1-m}$ of labour and $b B n^{-m}$ of waiting. The best crew is

$$n^* = \frac{m}{1-m}\,\frac{b}{w} = \frac{7}{3}\,\frac{b}{w} \quad (m = 0.7).$$

A storehouse that brings 10 woodcutters from 40 m to 10 m gives each
$0.61 - 0.43 = 0.18$ wood/s more: $b/w = 10 \times 0.18 / 0.43 = 4.2$, so
$n^* \approx 10$. The woodcutters build it themselves, in 8 s instead of
40.

**Search.** At each decision the candidates of each kind are generated
(the technologies available, the batch sizes, a house, the dropsite and
field sites next to the supplies that lose the most to walking, the barter
pairs), valued by $\Delta J$, and the best one with $\Delta J > 0$ is
inserted into the plan; this repeats until none is left. The number of
candidates looked at is a computing budget: it changes which options are
seen, never what an option is predicted to do. Greedy insertion is not
guaranteed optimal; its gap is measured against an exhaustive search on
small plans (validation).

## 7. Assignment

The forecast says how many workers of each group work each resource now.
The assignment says who goes where: each worker gets a place so as to
maximise

$$\sum_u r_u(s_u)\,\big(W(s_u) - t_{\text{walk}}(u, s_u)\big)$$

where $t_{\text{walk}}$ is the unit's walk to the place and $W(s)$ how long
the place keeps its rate in the forecast (until its front moves past it or
is exhausted, or the end of the plan). It is a transport problem (workers
to places, $M_s$ places per supply), solved exactly.

A busy worker is moved only when the gain over $W$ exceeds what moving
costs: its walk, and the load it would drop when it changes resource
($\lambda_k$ times what it carries). A worker on its way back to a dropsite
is moved when it has dropped its load, which costs nothing. These costs
come from the model; no threshold is needed to keep the assignment stable.

## 8. Scope

Covered: trees, rocks, mines, bushes, fields, carcasses, fish (ships and
docks are groups and dropsites like the others), treasures (a supply
collected on arrival: its value is $\lambda_k A_s$ against the walk),
resource trickles (a constant flow added to the stock, `ResourceTrickle`),
barter.

Not yet covered, each to be submitted before it is added: hunting (kill
and chase time before the carcass), corrals, trade between markets,
tribute, loot, and the risk of a site near the enemy (a policy decides
which sites are allowed).

## 9. Neglected

| Term | Size |
|---|---|
| The walk is a straight line; the path goes around obstructions | to measure (scenario `cycle`) |
| Time between a load and the next state of the unit (engine turns) | to measure (`cycle`) |
| Congestion around a dropsite | to measure (`crowd`) |
| Loads and workers are whole; the forecast treats them as a flow | at most one load per worker |
| A front is used from the dropsite outward; gatherers actually take the supply nearest to them | to measure (`front`) |
| Places are ranked by the rate of one group, then shared by all | to measure on mixed workforces (`front`) |
| Greedy insertion of decisions | to measure against exhaustive search (`plan`) |

## 10. Validation

Each scenario sets up the situation in the engine and compares the
measured quantity with the model's prediction.

| Scenario | Measures | Against |
|---|---|---|
| `cycle` | one gatherer per unit group and supply type, $d$ from 2 to 100 m | $r_g(s, 1)$ |
| `crowd` | $n$ gatherers on one field, one mine, one tree cluster; $n$ builders on one building | $\varphi_s(n)$; $B / n^m$ |
| `front` | a woodline with a storehouse, 5 to 40 woodcutters, until exhaustion | $Q(t)$ from $d_f(Q)$ |
| `train` | batches of 1 to 10 at each kind of building | $t_1 b^\beta \mu$ |
| `barter` | a sequence of deals with pauses | $e_{jk}$ and $\delta(t)$ |
| `plan` | a fixed plan from the start of a game against an idle player, on several maps | $T_i$ of the forecast, and $J$ against the exhaustive optimum on short plans |

The economy as a whole is measured on `plan`: the bot's $J$ against the
forecast optimum for the same start, and against Louis's play of the same
plan on the same maps.
