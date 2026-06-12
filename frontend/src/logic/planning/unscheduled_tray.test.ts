import { describe, expect, it } from 'vitest';

import type {
  LevelResponse,
  MatchWithDetails,
  StageItemWithRounds,
  StageWithStageItems,
} from '@openapi';
import type { MatchLookupEntry } from '@services/lookups';
import {
  groupUnscheduledMatchesForTray,
  nextTrayOpenedAfterPlannerEvent,
} from './unscheduled_tray';

function level(id: number, name: string, position: number): LevelResponse {
  return { id, name, position };
}

function match(id: number): MatchWithDetails {
  return { id } as MatchWithDetails;
}

function stage(
  id: number,
  name: string,
  levelId: number | null,
  stageItems: StageItemWithRounds[] = []
): StageWithStageItems {
  return { id, name, level_id: levelId, stage_items: stageItems } as StageWithStageItems;
}

function stageItem(id: number, name: string): StageItemWithRounds {
  return { id, name } as StageItemWithRounds;
}

function entry(
  matchDetails: MatchWithDetails,
  parentStage: StageWithStageItems,
  parentStageItem: StageItemWithRounds
): MatchLookupEntry {
  return {
    match: matchDetails,
    stage: parentStage,
    stageItem: parentStageItem,
  };
}

describe('groupUnscheduledMatchesForTray', () => {
  it('groups matches by level position and then by stage, skipping empty groups', () => {
    const beginner = level(10, 'Beginner', 1);
    const advanced = level(20, 'Advanced', 0);
    const groupA = stageItem(100, 'Group A');
    const groupB = stageItem(101, 'Group B');
    const advancedGroups = stage(200, 'Groups', advanced.id, [groupA]);
    const beginnerGroups = stage(201, 'Groups', beginner.id, [groupB]);
    const advancedFinals = stage(202, 'Finals', advanced.id, []);
    const matches = [match(1), match(2), match(3)];
    const lookup: Record<number, MatchLookupEntry> = {
      1: entry(matches[0], beginnerGroups, groupB),
      2: entry(matches[1], advancedGroups, groupA),
      3: entry(matches[2], advancedGroups, groupA),
      99: entry(match(99), advancedFinals, groupA),
    };

    expect(groupUnscheduledMatchesForTray(matches, lookup, [beginner, advanced])).toEqual({
      kind: 'grouped',
      levels: [
        {
          id: advanced.id,
          name: advanced.name,
          stages: [
            {
              id: advancedGroups.id,
              name: advancedGroups.name,
              matches: [matches[1], matches[2]],
            },
          ],
        },
        {
          id: beginner.id,
          name: beginner.name,
          stages: [
            {
              id: beginnerGroups.id,
              name: beginnerGroups.name,
              matches: [matches[0]],
            },
          ],
        },
      ],
    });
  });

  it('keeps no-level tournaments as one flat match list', () => {
    const matches = [match(1), match(2)];

    expect(groupUnscheduledMatchesForTray(matches, {}, [])).toEqual({
      kind: 'flat',
      matches,
    });
  });
});

describe('nextTrayOpenedAfterPlannerEvent', () => {
  it('collapses while placing a tray match and restores after placement or cancel', () => {
    expect(
      nextTrayOpenedAfterPlannerEvent({
        opened: true,
        previousSelection: { kind: 'idle' },
        nextSelection: { kind: 'tray-match-selected', matchId: 30 },
        event: { type: 'tap-tray-match', matchId: 30 },
        actions: [],
      })
    ).toBe(false);

    expect(
      nextTrayOpenedAfterPlannerEvent({
        opened: false,
        previousSelection: { kind: 'tray-match-selected', matchId: 30 },
        nextSelection: { kind: 'idle' },
        event: { type: 'tap-insertion-line', courtId: 1, index: 0 },
        actions: [
          {
            type: 'reschedule',
            matchId: 30,
            body: {
              old_court_id: null,
              old_position: null,
              new_court_id: 1,
              new_position: 0,
            },
          },
        ],
      })
    ).toBe(true);

    expect(
      nextTrayOpenedAfterPlannerEvent({
        opened: false,
        previousSelection: { kind: 'tray-match-selected', matchId: 31 },
        nextSelection: { kind: 'idle' },
        event: { type: 'cancel' },
        actions: [],
      })
    ).toBe(true);
  });
});
