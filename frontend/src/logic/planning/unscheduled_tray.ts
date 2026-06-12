import type { LevelResponse, MatchWithDetails } from '@openapi';
import type { MatchLookupEntry } from '@services/lookups';
import type { PlannerEvent, PlanningAction, SelectionState } from './selection';

export type TrayStageGroup = {
  id: number;
  name: string;
  matches: MatchWithDetails[];
};

export type TrayLevelGroup = {
  id: number | null;
  name: string;
  stages: TrayStageGroup[];
};

export type TrayMatchGroups =
  | { kind: 'flat'; matches: MatchWithDetails[] }
  | { kind: 'grouped'; levels: TrayLevelGroup[] };

export function groupUnscheduledMatchesForTray(
  matches: MatchWithDetails[],
  matchesLookup: Record<number, MatchLookupEntry>,
  levels: LevelResponse[]
): TrayMatchGroups {
  if (levels.length === 0) {
    return { kind: 'flat', matches };
  }

  const levelOrder = new Map(levels.map((level) => [level.id, level]));
  const levelsById = new Map<number | null, TrayLevelGroup>();
  const stagesByLevelAndId = new Map<string, TrayStageGroup>();

  for (const match of matches) {
    const entry = matchesLookup[match.id];
    if (entry == null) continue;

    const levelId = entry.stage.level_id;
    const level = levelId == null ? null : levelOrder.get(levelId);
    const levelGroup = getOrInsert(levelsById, levelId, () => ({
      id: levelId,
      name: level?.name ?? '',
      stages: [],
    }));
    const stageKey = `${levelId ?? 'none'}:${entry.stage.id}`;
    const stageGroup = getOrInsert(stagesByLevelAndId, stageKey, () => {
      const group = {
        id: entry.stage.id,
        name: entry.stage.name,
        matches: [],
      };
      levelGroup.stages.push(group);
      return group;
    });

    stageGroup.matches.push(match);
  }

  return {
    kind: 'grouped',
    levels: [...levelsById.values()].sort((a, b) => {
      const levelA = a.id == null ? null : levelOrder.get(a.id);
      const levelB = b.id == null ? null : levelOrder.get(b.id);
      return (
        (levelA?.position ?? Number.MAX_SAFE_INTEGER) -
        (levelB?.position ?? Number.MAX_SAFE_INTEGER)
      );
    }),
  };
}

export function nextTrayOpenedAfterPlannerEvent({
  opened,
  previousSelection,
  nextSelection,
  event,
  actions,
}: {
  opened: boolean;
  previousSelection: SelectionState;
  nextSelection: SelectionState;
  event: PlannerEvent;
  actions: PlanningAction[];
}): boolean {
  if (nextSelection.kind === 'tray-match-selected') {
    return false;
  }

  if (previousSelection.kind !== 'tray-match-selected') {
    return opened;
  }

  if (event.type === 'cancel' || actions.length > 0) {
    return true;
  }

  return opened;
}

function getOrInsert<K, V>(map: Map<K, V>, key: K, create: () => V): V {
  const existing = map.get(key);
  if (existing != null) return existing;

  const value = create();
  map.set(key, value);
  return value;
}
