import { MatchSet, MatchState, MatchWithDetails } from '@openapi';

export type ScoreTrackingViewState =
  | { kind: 'not_started' }
  | { kind: 'playing'; set: MatchSet }
  | { kind: 'between_sets'; completed: MatchSet; next: MatchSet; allSets: MatchSet[] }
  | { kind: 'completed' };

export function getScoreTrackingViewState(
  sets: MatchSet[],
  matchState?: MatchState
): ScoreTrackingViewState {
  // A COMPLETED match is final even when not every set was played (best-of-n mode ends the
  // match at a set-win majority), so never offer a next set on it.
  if (matchState === 'COMPLETED') return { kind: 'completed' };

  const inProgress = sets.find((s) => s.state === 'IN_PROGRESS');
  if (inProgress) return { kind: 'playing', set: inProgress };

  const lastCompleted = [...sets].reverse().find((s) => s.state === 'COMPLETED');
  const nextNotStarted = sets.find((s) => s.state === 'NOT_STARTED');

  if (lastCompleted && nextNotStarted) {
    return { kind: 'between_sets', completed: lastCompleted, next: nextNotStarted, allSets: sets };
  }
  if (sets.every((s) => s.state === 'NOT_STARTED')) {
    return { kind: 'not_started' };
  }
  return { kind: 'completed' };
}

// Unplayed sets on a completed match were never played (best-of-n ended the match early), so
// score displays hide them: a Bo3 won 2-0 shows two sets.
export function getVisibleSets<S extends Pick<MatchSet, 'state'>>(match: {
  state: MatchState;
  match_sets: S[];
}): S[] {
  if (match.state !== 'COMPLETED') return match.match_sets;
  return match.match_sets.filter((s) => s.state !== 'NOT_STARTED');
}

export function getDisplayScores(
  set: Pick<MatchSet, 'stage_item_input1_score' | 'stage_item_input2_score'>,
  isSwapped: boolean
): { first: number; second: number } {
  return isSwapped
    ? { first: set.stage_item_input2_score, second: set.stage_item_input1_score }
    : { first: set.stage_item_input1_score, second: set.stage_item_input2_score };
}

export type HighlightedDisplayScore = { value: number; isHigher: boolean };

export function getHighlightedDisplayScores(
  set: Pick<MatchSet, 'stage_item_input1_score' | 'stage_item_input2_score'>,
  isSwapped: boolean
): { first: HighlightedDisplayScore; second: HighlightedDisplayScore } {
  const { first, second } = getDisplayScores(set, isSwapped);
  return {
    first: { value: first, isHigher: first > second },
    second: { value: second, isHigher: second > first },
  };
}

export function nextScoresAfterAdjust(
  set: Pick<MatchSet, 'stage_item_input1_score' | 'stage_item_input2_score'>,
  slot: 1 | 2,
  delta: number
): { stage_item_input1_score: number; stage_item_input2_score: number } {
  return {
    stage_item_input1_score: Math.max(0, set.stage_item_input1_score + (slot === 1 ? delta : 0)),
    stage_item_input2_score: Math.max(0, set.stage_item_input2_score + (slot === 2 ? delta : 0)),
  };
}

// Order scheduled matches the way they play out on a court: by start time (matches without a start
// time sort last), breaking ties by id for a stable ordering.
function compareMatchesByScheduleThenId(a: MatchWithDetails, b: MatchWithDetails): number {
  if (a.start_time !== b.start_time) {
    if (a.start_time == null) return 1;
    if (b.start_time == null) return -1;
    return a.start_time < b.start_time ? -1 : 1;
  }
  return a.id - b.id;
}

// Given the full list of scheduled matches and the current match, find the next match on the same
// court that still needs to be played (i.e. is not completed). Returns null when there is none.
export function getNextMatchOnCourt(
  matches: MatchWithDetails[],
  currentMatch: MatchWithDetails
): MatchWithDetails | null {
  if (currentMatch.court_id == null) return null;

  const sameCourt = matches
    .filter((match) => match.court_id === currentMatch.court_id)
    .sort(compareMatchesByScheduleThenId);

  const currentIndex = sameCourt.findIndex((match) => match.id === currentMatch.id);
  if (currentIndex === -1) return null;

  for (let i = currentIndex + 1; i < sameCourt.length; i += 1) {
    if (sameCourt[i].state !== 'COMPLETED') return sameCourt[i];
  }
  return null;
}

export function isEndSetDisabled(
  set: MatchSet,
  match: {
    two_point_advantage: boolean;
    max_points: number;
    last_set_max_points: number | null;
    num_sets: number;
    draws_allowed: boolean;
  },
  isSwapped: boolean
): boolean {
  const { two_point_advantage, max_points, last_set_max_points, num_sets, draws_allowed } = match;
  const limit =
    set.set_number === num_sets && last_set_max_points != null ? last_set_max_points : max_points;
  const s1 = isSwapped ? set.stage_item_input2_score : set.stage_item_input1_score;
  const s2 = isSwapped ? set.stage_item_input1_score : set.stage_item_input2_score;
  const maxScore = Math.max(s1, s2);
  if (maxScore < limit) return true;
  if (two_point_advantage && Math.abs(s1 - s2) < 2) return true;
  if (!draws_allowed && s1 === s2) return true;
  return false;
}
