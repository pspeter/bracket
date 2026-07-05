# Bracket

Tournament system: a Club runs Tournaments; a Tournament has Stages; a Stage has Stage Items
(a round-robin group, a single-elimination bracket, or a Swiss group); a Stage Item has Rounds
of Matches. Stage Items connect via Stage Item Inputs, which reference either a team directly
or a ranking position of another Stage Item.

## Language

**Standings**:
The ranking-derived order of a Stage Item's inputs, computed from completed matches
(points/ELO, set difference, point difference).
_Avoid_: leaderboard, table

**Reconciliation**:
Bringing every standings-derived structure back in line after anything moves a Stage Item's
standings: team statistics, Swiss round pairings, elimination-tree inputs, and cross-stage
inputs that reference the item's final ranking. Callers state *that* standings moved; the
reconciliation module decides what follows.
_Avoid_: recalculation-cascade, propagation (as a noun for the whole concept)

**Resolution**:
Filling a placeholder with a concrete team: a Swiss Round is *resolved* when its matches get
teams assigned; a Stage Item Input is *resolved* when its "winner of X" reference is replaced
by an actual team.
_Avoid_: activation (the old manual-stage-activation term), assignment
