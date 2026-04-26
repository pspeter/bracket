/** Mirrors backend `max_until_rank_for_template` / template `_max_rank`. */
export function maxUntilRankForTemplate(groups: 2 | 4, totalTeams: number): number {
  if (groups === 4) {
    return 8;
  }
  return Math.floor(totalTeams / groups) * 2;
}

export function resolveUntilRank(
  untilRank: 'all' | number,
  groups: 2 | 4,
  totalTeams: number
): number {
  const maxRank = maxUntilRankForTemplate(groups, totalTeams);
  return untilRank === 'all' ? maxRank : untilRank;
}

/** Group sizes for display (Group A gets remainder first), same as backend ordering. */
export function groupTeamCounts(totalTeams: number, groups: 2 | 4): number[] {
  const base = Math.floor(totalTeams / groups);
  const remainder = totalTeams % groups;
  return Array.from({ length: groups }, (_, i) => base + (i < remainder ? 1 : 0));
}

export function knockoutMatchLabels(
  groups: 2 | 4,
  totalTeams: number,
  includeSemiFinal: boolean,
  resolvedUntilRank: number
): string[] {
  const tpg = Math.floor(totalTeams / groups);

  if (groups === 4) {
    const out = ['Semi-final A', 'Semi-final B', 'Final'];
    if (resolvedUntilRank >= 4) {
      out.push('3rd Place');
    }
    if (resolvedUntilRank >= 6) {
      out.push('5th-8th Semi A', '5th-8th Semi B', '5th Place');
    }
    if (resolvedUntilRank >= 8) {
      out.push('7th Place');
    }
    return out;
  }

  if (includeSemiFinal) {
    const out = ['Semi-final A', 'Semi-final B', 'Final'];
    if (resolvedUntilRank >= 4) {
      out.push('3rd Place');
    }
    const placeNames = ['5th Place', '7th Place', '9th Place', '11th Place'];
    for (let position = 3; position <= tpg; position += 1) {
      const rank = 4 + (position - 2) * 2;
      if (rank > resolvedUntilRank) {
        break;
      }
      const i = position - 3;
      out.push(i < placeNames.length ? placeNames[i]! : `${rank - 1}th Place`);
    }
    return out;
  }

  const placeNames = ['Final', '3rd Place', '5th Place', '7th Place'];
  const out: string[] = [];
  for (let i = 0; i < tpg; i += 1) {
    const rank = (i + 1) * 2;
    if (rank > resolvedUntilRank) {
      break;
    }
    out.push(i < placeNames.length ? placeNames[i]! : `${rank - 1}th Place`);
  }
  return out;
}

/** English ordinal suffix only (e.g. 2 → "nd" for "2nd"). */
export function englishOrdinalSuffix(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) {
    return 'th';
  }
  switch (n % 10) {
    case 1:
      return 'st';
    case 2:
      return 'nd';
    case 3:
      return 'rd';
    default:
      return 'th';
  }
}

export function evenRankOptions(maxRank: number): number[] {
  const out: number[] = [];
  for (let r = 2; r <= maxRank; r += 2) {
    out.push(r);
  }
  return out;
}
