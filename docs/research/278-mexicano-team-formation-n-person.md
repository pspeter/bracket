# Research: N-person team-formation algorithms for rotating-format ("true Mexicano") tournaments

Wayfinder ticket: [pspeter/bracket#278](https://github.com/pspeter/bracket/issues/278)

## Methodology note (read this before the sources below)

This session's outbound HTTP tooling runs through an organization-managed egress proxy. Direct
page fetches (`WebFetch`) to most of the small tournament-format sites cited below were rejected
by the proxy with a policy-level 403 (confirmed via the proxy's own status endpoint, which logs
`connect_rejected` / "policy denial" for hosts including `docs.padelfast.com`,
`helpmanager.playtomic.com`, `padelamericanos.com`, and `www.azregionvolleyball.org`). Per the
environment's own instructions, blocked hosts must be reported, not routed around. `WebFetch` was
not universally broken, though — it succeeded for `github.com`, which is cited directly below.

As a result, most of the claims below are grounded in **web-search-engine synthesis** of those
pages (which quotes and paraphrases the live page content and cites the URL) rather than a
directly-fetched, independently-verified full page read. I treat that as weaker than a primary
source I read myself, and flag it inline as "(search-synthesis, not directly fetched)". Two
sources — a GitHub repository and this project's own source code — *were* read directly and are
marked "(fetched directly)". Where I could find no source at all beyond common knowledge (chiefly
"snake draft" itself), I say so explicitly rather than inventing a citation, per the task
instructions.

---

## 1. Algorithms found

### 1.1 Padel/tennis Mexicano — the 2-person baseline being generalized

**What it specifies:** Round 1 is a random draw. After every round, players are sorted by
cumulative points (ties broken by set/game difference, depending on the variant). The sorted
field is split into consecutive blocks of 4 — one block per court, strongest court first. Within
each block of 4, the pairing is `rank1+rank4` vs `rank2+rank3`. The next block (ranks 5–8) forms
the next court the same way, and so on. Sources converge that `1+4 vs 2+3` is the dominant
convention because it minimizes the rank-sum gap between the two teams (5 vs 5, vs. `1+3 vs 2+4`'s
4 vs 6); a minority of organizers instead use `1+3 vs 2+4`. There is no single sport federation
that governs amateur Mexicano/Americano the way FIVB governs volleyball, so "the rule" is really
an app/organizer convention, not a codified sport law.

**Source:** Converging descriptions across multiple padel-format guides — [Padel Fast: Mexicano
format](https://www.padelfast.com/formats/mexicano),
[americano-padel.app: Mexicano padel rules and format guide](https://americano-padel.app/en/blog/mexicano-padel-rules-format-guide/),
[Pistas365: Mexicano Padel Tournament rules](https://pistas365.com/padel/information/rules/mexicano-tournament/),
[Live For Padel: What Is Padel Mexicano?](https://www.liveforpadel.com/blog/padel-mexicano-rules)
(search-synthesis, not directly fetched — all four hosts returned proxy policy denials on direct
fetch).

### 1.2 Playtomic Manager — first-party Mexicano + "King of the Court" tournament tooling

**What it specifies:** Playtomic (a padel/tennis court-booking and tournament SaaS company) ships
Mexicano, Americano, and a padel-specific "King of the Court" tournament tool in its Manager
product. Its Mexicano tool follows the same live-leaderboard reshuffle described in 1.1: results
are entered match-by-match, the leaderboard updates in real time, and the next round's pairings
are generated from current standings. Its "King of the Court" tool is a different mechanic — a
ladder/queue format where the winning pair stays on the "king" court and challengers rotate in
from a queue; the organizer chooses the *initial* player distribution (stacked, balanced, or
random) but there is no documented rank-crossing formula for re-forming teams round to round — the
team roster is fixed once you're in the queue, and the queue/rotation is what changes.

**Source:** [Playtomic Manager Help Center — "New Tournament Tools: King of the Court, Americano,
and Mexicano"](https://helpmanager.playtomic.com/hc/en-gb/articles/44129657203985-New-Tournament-Tools-King-of-the-Court-Americano-and-Mexicano),
published by Playtomic itself (search-synthesis, not directly fetched — host returned a proxy
policy denial).

### 1.3 "Team Mexicano" — fixed 2-person teams, rank-based re-matching only

**What it specifies:** A named variant where teams are fixed for the whole tournament (pre-formed
duos), and only the **matchups between teams** are re-paired each round by current team standings
— "best-ranked teams face best-ranked teams." No player-level reshuffling happens; this is
matchup-rebalancing, not team-formation. I found no documented extension of this variant to teams
larger than 2.

**Source:** [americano-padel.com — Team Mexicano/Americano](https://www.americano-padel.com/team-mexicano-americano/en)
(search-synthesis, not directly fetched — host returned a proxy policy denial).

**This is directly relevant to Bracket's own codebase**: reading
`backend/bracket/logic/scheduling/mexicano_round_pairing.py` and
`backend/bracket/logic/scheduling/mexicano_skeleton.py` (fetched directly — these are this
project's own files) shows Bracket's *existing* Mexicano implementation is architecturally
exactly this "Team Mexicano" pattern: `select_mexicano_round_pairing` takes already-formed
`StageItemInput` entries, sorts them by points/set-difference/point-difference/slot, and pairs
them adjacently (`ordered[0]` vs `ordered[1]`, `ordered[2]` vs `ordered[3]`, ...) into matches each
round. Its docstring is explicit that "Rematches are allowed — unlike Swiss no history is
consulted for pairing." It does **not** re-form team membership from individual players — that is
precisely the missing capability #278 is scoping. The existing bye-rotation logic in `_pick_bye`
(fewest byes so far, ties broken by ascending slot) is a useful, already-established pattern worth
reusing for the N-person case.

### 1.4 Volleyball "King of the Court" — ladder/queue, not rank-crossing team formation

**What it specifies:** Multiple teams queue for one court; one side is the "king" side, the other
the "challenger" side. Whoever wins the rally/set stays; the loser rotates out and the next
queued team rotates in. Team rosters are typically fixed at check-in (you show up with your
crew, or an organizer assigns rosters once at the start) — the format governs *who plays whom
next*, not *how teams are built from a ranked individual pool* each round. I found no primary
source describing an ongoing, points-driven reshuffling of individual players into new teams
within King of the Court itself.

**Sources:** [kingofthecourt.com — Rules of the Game](https://kingofthecourt.com/rules-of-the-game),
[AVP Beach Volleyball — King of the Court series](https://avp.com/king-of-the-court-series/),
[b2bvolleyball.com — King of the Court Tournament Format](https://play.b2bvolleyball.com/blog/king-of-the-beach-tournament-format)
(search-synthesis, not directly fetched — `kingofthecourt.com` returned a proxy policy denial;
the others were not attempted directly given the pattern). Note none of these is a governing-body
rulebook (FIVB's official rules PDF and USA Volleyball's rules page were located but describe
standard 6v6 volleyball, not King of the Court specifically) — King of the Court appears to be a
club/vendor-level convention, not a codified format with one canonical source.

### 1.5 Snake draft — the general N-team generalization, mostly "well-known convention"

**No single canonical primary source exists for "snake draft" itself** — as the task anticipated,
this is common knowledge from fantasy sports and pickup-game team-picking, not a citable
invention. I looked for the closest things to authoritative treatments:

- **Academic, secondhand only:** Brams & Straffin (1979), *"Prisoners' Dilemma and Professional
  Sports Drafts"* — an early game-theoretic analysis of draft-order fairness, but limited to
  simplified 2–3 team, complete-information cases. I could not fetch this paper directly; I only
  have it via a citation inside a Washington University in St. Louis course report, ["Altering
  Draft Order in an Attempt to Create Fairness"](https://www.cs.wustl.edu/~cytron/cake/Reports/PDFs/football.pdf)
  (also not directly fetchable — proxy policy denial). Per search-synthesis, that report compares
  standard "snake"/serpentine ordering, "adjusted order" (next pick goes to whichever team has
  accumulated the least value so far), and "least-first" ordering, using the standard deviation of
  final team value as the fairness metric, and reports adjusted/least-first as marginally more
  equitable than plain snake — but snake remains the simplest and most widely used. **This whole
  bullet is secondhand (search-synthesis of an unfetched PDF citing an unfetched 1979 paper) —
  treat as a pointer to follow up on, not a verified finding.**
- **Practical tool, fetched directly:** [GitHub — Xwoe/matchmaking](https://github.com/Xwoe/matchmaking)
  is a small first-party open-source tool for splitting rated players into balanced teams. Its
  README (read directly) describes a two-stage approach: seed teams by tiering players into groups
  matching team size and crossing top/bottom tiers (a snake-like seed), then run an **iterative
  local-search optimizer** that swaps players between teams to minimize "the maximum deviation a
  team has from the total average skill rating," stopping at convergence or an iteration cap. This
  confirms snake-style seeding is the natural starting point developers reach for, but shows a
  real project going a step further with post-hoc optimization for a strictly better fairness
  guarantee than snake alone provides.
- **Practical tool, search-synthesis only:** [toolsmatic.me — Team Balancer](https://toolsmatic.me/tools/team-balancer.html)
  states in its own copy that it "uses a snake draft because it is one of the easiest balancing
  methods to explain and one of the most reliable for small and medium groups" — ranks players by
  skill, assigns forward through teams (A, B, C, ...), then reverses direction each round. A
  first-party (if informal) vendor statement of plain snake draft for N-team skill balancing.
  (Not directly fetched — proxy policy denial.)
- **Sports-context example of the identical mathematical pattern:** a Northern Lights Juniors
  (a real junior volleyball club) document, ["Snake-Seed-Examples.pdf"](https://www.northernlightsjuniors.org/wordpress/wp-content/uploads/2016/08/Snake-Seed-Examples.pdf),
  describes snake-seeding numbered *seeds* across *pools* for bracket/pool-play balancing (seed 1
  → pool A, seed 2 → pool B, ... reverse each pass) — the identical boustrophedon pattern applied
  to pools instead of in-round rotating teams. (Not directly fetched — search-synthesis only.)

### 1.6 Academic "balanced team formation" literature (general CS, not sports-specific)

A cluster of arXiv papers treats "balanced team formation from a rated pool" as an optimization
problem, generally minimizing either variance or max-deviation-from-mean of team skill/workload:
["Finding teams that balance expert load and task coverage"](https://arxiv.org/pdf/2011.04428),
["A Team-Formation Algorithm for Faultline Minimization"](https://arxiv.org/pdf/1811.05015),
["FERN: Fair Team Formation for Mutually Beneficial Collaborative Learning"](https://arxiv.org/pdf/2011.11611).
These are workplace/education team-formation papers, not sports-format papers, and I was only able
to review search-engine abstract-level summaries (direct PDF fetch was blocked). They're useful as
background theory for *why* rank-crossing/snake heuristics approximate a variance-minimizing
objective, not as sports-specific citations. A related practitioner writeup — [Lucas Moda, "An
algorithm to generate balanced pickup soccer teams" (Medium)](https://lukmoda.medium.com/an-algorithm-to-generate-balanced-pickup-soccer-teams-26141556f854)
— describes computing per-team average rating and minimizing the max–min spread across teams, the
same objective as Xwoe/matchmaking above (also search-synthesis only, not directly fetched).

---

## 2. Tradeoffs

| | Fairness | Predictability / gameability | Repeat-grouping avoidance |
|---|---|---|---|
| **Padel Mexicano crossover (1+4/2+3, blocked by court)** | Within a match, near-optimal: rank-sum spread between the two teams is minimized by construction (see §3 for the proof sketch). Across courts, it's deliberately *graduated* — court 1 always has the strongest players, court 2 the next tier, etc. — not globally mixed. | Fully deterministic given the live leaderboard; any player can compute their next team/opponent themselves. This is good for transparency but is a known vector for "sandbagging" (underperforming to draw an easier bracket). | Not addressed at all. It's purely a function of the current standings snapshot; the same two strong players can be re-paired or re-opposed round after round. |
| **Team Mexicano / Bracket's existing `mexicano_round_pairing.py`** | Rebalances *opponents* each round but never rebalances *team composition* — a team's internal skill disparity is fixed for the whole tournament. Doesn't solve the player-Mexicano problem at all; it solves a different, already-handled problem (matchup rebalancing for static teams). | Same as above: deterministic adjacent-pairing by standings. | Explicitly documented as unaddressed by design ("Rematches are allowed"). |
| **King of the Court (padel or volleyball)** | No round-by-round rebalancing mechanism; fairness depends entirely on how rosters were assigned once, at the start. A weak team can be stuck as weak for the whole session. | Rotation queue order is visible/predictable, but which specific *team* you're on isn't rank-driven — it's whoever you showed up with, or an initial-only balancing pass. | Not applicable — teams don't reform, so "repeat teammates" isn't a concept; repeat *opponents* is inherent to the ladder structure. |
| **Snake draft (general N-team generalization)** | Provably minimizes rank-sum spread across N teams for a rank-order-only algorithm (each team gets one "high" and one "low" pick per full pass) — this is the same property that makes 1+4/2+3 preferred over 1+3/2+4 in padel (§3). Strictly worse than an iterative swap-optimizer (Xwoe/matchmaking) if points/skill are cardinal, not just ordinal, since snake only uses rank order, not magnitude. | Deterministic and fully computable by any participant from the public leaderboard, same gameability profile as the padel rule. Randomizing tie-breaks (as Bracket's own bye-picker already does) reduces this at the margin. | Not addressed inherently — it's a pure function of the current ranking, with no memory. Needs a separate history-aware layer, exactly as Bracket's Swiss format already does (consults match history; Mexicano formats explicitly do not). |
| **Iterative swap-optimization (Xwoe/matchmaking style)** | Strictly better than snake alone on the stated objective (minimizes max deviation from mean team skill directly, rather than approximating it via traversal order), especially when points are cardinal (not just rank). | Less hand-computable by a player standing courtside — the *objective* is public but the *exact resulting assignment* depends on iteration/seed, so it's harder to game deliberately, at some cost to perceived transparency. | Same as snake: no inherent memory; would need the same bolted-on history layer. |
| **Ladder/queue formats generally** | Weakest fairness guarantee of the group for round-by-round team composition, since they don't attempt it. | High — the rotation order is usually the only variable, and it's visible. | N/A (rosters don't reform). |

**Summary:** every rank-based reshuffling algorithm found (padel Mexicano, its Playtomic
implementation, snake draft, and the swap-optimizer) is a pure function of the *current* ranking
snapshot and inherently allows repeat groupings — this is a deliberate, shared design choice across
real Mexicano-style formats and matches how Bracket's own 2-person Mexicano already works, not an
oversight. Repeat-avoidance, where it exists at all in ranked/rotating formats (e.g. Swiss), is
always a distinct add-on layer that consults history, not something baked into the rank-crossing
formula itself.

---

## 3. Recommendation: block-then-snake as the default N-person "true Mexicano" algorithm

### The procedure

Each round, given the set of currently-active individual players and a configured team size `N`:

1. **Rank the pool.** Sort active players by the same tiebreak chain Bracket's existing Mexicano
   code already uses for teams: cumulative points, then set difference, then point difference,
   then input slot (for round 1, before any points exist, this reduces to builder input order —
   reuse that convention unchanged).
2. **Determine match count and byes.** Each match needs `2N` players (two teams of `N`). With `P`
   active players, `C = floor(P / (2N))` matches are playable this round; the `P - 2N*C` leftover
   players sit out. Pick who sits out with the same fewest-byes-so-far-then-ascending-slot rule
   Bracket's `_pick_bye` already implements for the 2-person case, generalized from "1 possible
   bye" to "0 to `2N-1` possible byes."
3. **Partition into blocks of `2N`, strongest block first.** After removing byes, slice the sorted
   list into consecutive blocks of `2N` players: players ranked `1..2N` are Court 1's full player
   pool, `2N+1..4N` are Court 2's, and so on. This preserves the real Mexicano property that court
   1 is always the highest-stakes court (best players playing each other), not a global mixing of
   strength across courts.
4. **Snake-split each block into two teams of `N`.** Within a block's own local ranking
   (`1..2N`), assign players to Team A / Team B in strict boustrophedon (snake) order: pick 1 →
   A, pick 2 → B, pick 3 → B, pick 4 → A, pick 5 → A, pick 6 → B, ... (alternating direction every
   `N`-length lap). That is a snake draft run *within the block*, between exactly the block's two
   teams.
5. **The two teams from each block play each other** as that block's match.
6. **Repeat every round from scratch** — no persistence of prior team assignments, matching the
   existing Mexicano philosophy that "opponents [and, now, teammates] are re-drawn every round
   from current standings" and that rematches/repeat-teammates are allowed by default.

### Why this is the right generalization, not just *a* generalization

Run the procedure at `N=2` (a single block, no multi-court partitioning needed): block ranks
`1,2,3,4`, snake order A,B,B,A → Team A = `{rank1, rank4}`, Team B = `{rank2, rank3}`. **This is
exactly the padel `1+4 vs 2+3` rule**, recovered exactly, not approximated. At two courts (`N=2`,
8 players), block 1 (`ranks 1–4`) reproduces `1+4 vs 2+3`, block 2 (`ranks 5–8`) reproduces `5+8 vs
6+7` — exactly the multi-court pattern described in the padel sources in §1.1. This is also why
`1+4/2+3` is favored over `1+3/2+4` in practice: `1+4` and `2+3` both sum to 5 (a perfectly
balanced split), while `1+3`/`2+4` sum to 4 and 6 (an avoidable imbalance) — `1+4/2+3` **is** the
snake-draft split, and `1+3/2+4` is not.

The same balance property holds for `N>2` and isn't just a coincidence at `N=2`: a snake draft
over `2N` sequentially-ranked values always produces the minimum possible sum-spread between the
two `N`-sized halves. For `N=3` (ranks 1–6), the split is Team A = `{1,4,5}` (sum 10), Team B =
`{2,3,6}` (sum 11) — spread 1, which is the theoretical minimum for splitting six consecutive
integers into two groups of three (their total, 21, is odd, so 1 is the best any split can do).
This gives a concrete, provable fairness argument for the default, not just "snake draft is
common practice."

**Reconciling with the tradeoffs in §2:**
- *Fairness*: optimal for a rank-order-only algorithm, and provably reduces to the real padel rule
  at N=2 — no regression versus the format this is generalizing, and no hand-wavy justification
  needed for N>2.
- *Predictability*: identical gameability profile to today's 2-person Mexicano (fully
  deterministic from the public leaderboard) — this is a conscious non-regression, not an
  oversight; if the project later wants less predictability, that's a natural place to swap in a
  variant strategy (see §4) that randomizes within tied-points buckets, rather than a change to
  this default.
- *Repeat-grouping avoidance*: **not included by default**, matching every real-world rank-based
  format surveyed (padel Mexicano, Playtomic's implementation, and Bracket's own existing 2-person
  Mexicano code, whose docstring explicitly allows rematches) and consistent with this project's
  own precedent of keeping that concern in the Swiss format's separate history-aware pairing logic
  instead. If repeat-avoidance is wanted for player-Mexicano later, it should be a distinct,
  optional constraint pass over the block-then-snake output (e.g., re-roll or locally swap
  players within a block if the resulting team composition exactly repeats a recent round's
  teammates), not something folded into the snake formula itself.

An explicit alternative considered and rejected as the *default*: a single global snake pass
across the *entire* ranked field (not partitioned into blocks first) before assigning courts. This
would pair the single best player in the field with one of the very weakest as a teammate once the
snake reaches the bottom of a large field, and would mix strength levels across courts rather than
keeping court 1 the most competitive court — a real deviation from how padel Mexicano is actually
played and described in every source found in §1.1. Block-then-snake keeps the graduated-court
structure intentionally; this alternative is worth keeping available as a pluggable variant (see
§4) for operators who explicitly want cross-court mixing, but should not be the default.

---

## 4. Pluggable-strategy interface notes

This is a design note in prose — no interface is specified in code, and none should be written
against this document.

### Inputs a team-formation strategy needs

- **Ranked player pool for the stage item**: the same per-player shape Bracket's existing Mexicano
  pairing code already consumes for team-level entrants — an identity, current cumulative points,
  and the existing tiebreak fields (set difference, point difference, input slot). A strategy
  should receive this pre-filtered to "active" players only, mirroring the existing
  `active = [i for i in inputs if ...]` filter, so every strategy implementation doesn't have to
  re-derive activity/eligibility rules itself.
- **Team size `N`**: configured per stage item (2 up to 6+), not hardcoded.
- **Match/court count for this round** (or enough information to derive it — active player count
  and `N`): needed because it determines how many `2N`-blocks exist and thus how many byes are
  needed.
- **Round number / "is this the first round" flag**: round 1 has no standings yet and needs a
  defined fallback ordering (this project's existing convention: builder input order via the
  all-zero-points tiebreak chain) — a strategy needs to know whether it's operating on real
  standings or the pre-tournament fallback so it can apply that convention consistently, or a
  different one if a future strategy wants a genuinely random round-1 draw instead.
- **History of past groupings**: which players have been teammates before and which have been
  opponents before, across all prior rounds of this stage item. The *default* block-then-snake
  strategy can ignore this entirely, but the interface should still pass it through so that a
  future repeat-avoidance strategy (or a repeat-avoidance wrapper around the default) can consume
  it without changing what callers pass in.
- **Bye/availability state**: byes-so-far per player (for fair bye rotation) and any explicit
  sit-out/exclusion constraints (e.g., a player marked unavailable this round). This generalizes
  the existing `_pick_bye` bye-counting logic from "at most one bye per round" to "zero to `2N-1`
  byes per round."
- **A determinism/randomness seed** (optional but recommended): so that a given round's grouping
  is reproducible for debugging/support purposes even if a strategy has a randomized component
  (e.g., random tie-breaking within equal-points clusters, or the swap-optimizer approach from
  §1.5, which is iterative and could otherwise be non-deterministic run-to-run).

### Outputs a team-formation strategy needs to produce

- **List of teams for the round**: each a group of exactly `N` player IDs, tagged with a
  synthetic per-round team identity (teams in this format don't persist across rounds the way
  `StageItemInput` teams do today, so this output shape is necessarily different from — and sits
  upstream of — the existing team model).
- **List of matches**: pairs of the above per-round teams, each assigned to a court/match slot for
  this round. This is a logically separate decision from team *formation* — Bracket's existing
  `select_mexicano_round_pairing` already owns exactly this decision for pre-formed, persistent
  teams (adjacent pairing by standings). The block-then-snake design in §3 keeps this decision
  trivial (each block's two teams simply play each other), but a future team-formation strategy
  might produce per-round teams *without* also deciding who plays whom, in which case the existing
  match-pairing logic should be reusable as-is over the newly-formed teams' aggregate standings.
  The interface should keep these as two separable steps — team formation, then match pairing —
  even though the recommended default happens to make the second step trivial.
- **Bye/sit-out list for the round**: which players (if any) are excluded, so the byes-so-far
  count stays correct for next round's bye selection.
- **Optional fairness/observability metadata**: e.g., the rank-sum spread achieved for each match,
  so different strategies can be compared, monitored, or surfaced to organizers/players (e.g., "how
  balanced is this round") without requiring the caller to recompute it from the raw output.

### Why this shape keeps the strategy swappable

Keeping "team formation" (ranked players → per-round teams) and "match pairing" (per-round teams →
matches) as two distinct, independently swappable steps — rather than one monolithic function —
means a future contributor can:
- Replace only the team-formation half (e.g., swap block-then-snake for the iterative
  swap-optimizer approach from §1.5, or for a global-snake variant that intentionally mixes
  strength across courts) while reusing the existing match-pairing logic unchanged.
- Replace only the match-pairing half (e.g., add repeat-opponent avoidance as a history-aware
  variant) while reusing whatever team-formation strategy is configured.
- Layer a repeat-avoidance *wrapper* around either step without either step needing to know about
  history itself, consistent with how this project already keeps Swiss's history-aware pairing
  logic separate from Mexicano's history-blind pairing logic today.

Both steps should remain pure functions over their declared inputs (no direct database access),
matching the existing pattern in `mexicano_round_pairing.py` and `mexicano_skeleton.py` — those
files, along with their paired unit tests (`test_mexicano_round_pairing.py`,
`test_mexicano_skeleton.py`, `test_mexicano_slot_assigner.py`), demonstrate this project's existing
convention of testing pairing/formation logic as pure functions over plain data, without database
fixtures. Any new N-person team-formation strategy should be testable the same way.
