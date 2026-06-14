export type HighlightTarget =
  | { kind: 'team'; teamId: number; label: string }
  | { kind: 'stage-item-input'; inputId: number; label: string };

type MatchInputLike = {
  id?: number | null;
  team_id?: number | null;
  team?: { name?: string | null } | null;
  winner_from_stage_item_id?: number | null;
  winner_position?: number | null;
};

type MatchLike = {
  id: number;
  stage_item_input1?: MatchInputLike | null;
  stage_item_input2?: MatchInputLike | null;
  stage_item_input1_winner_from_match_id?: number | null;
  stage_item_input2_winner_from_match_id?: number | null;
};

type MatchLookupLike = Record<number, { match: MatchLike }>;

type StageLike = {
  stage_items?: Array<{
    id?: number | null;
    name?: string | null;
    inputs?: MatchInputLike[];
  }>;
};

export interface HighlightOption {
  value: string;
  label: string;
  target: HighlightTarget;
}

function inputInvolvesHighlight(input: MatchInputLike | null | undefined, target: HighlightTarget) {
  if (target.kind === 'team') return input?.team_id === target.teamId;
  return input?.id === target.inputId;
}

export function matchInvolvesHighlight(
  match: MatchLike,
  target: HighlightTarget | null,
  matchesLookup: MatchLookupLike
): boolean {
  if (target == null) return false;
  if (
    inputInvolvesHighlight(match.stage_item_input1, target) ||
    inputInvolvesHighlight(match.stage_item_input2, target)
  ) {
    return true;
  }

  const sourceMatchIds = [
    match.stage_item_input1_winner_from_match_id,
    match.stage_item_input2_winner_from_match_id,
  ].filter((id): id is number => id != null);

  return sourceMatchIds.some((sourceMatchId) => {
    const sourceMatch = matchesLookup[sourceMatchId]?.match;
    return sourceMatch != null && matchInvolvesHighlight(sourceMatch, target, matchesLookup);
  });
}

export function stageHighlightOptions(stages: StageLike[]): HighlightOption[] {
  const byTeamId = new Map<number, HighlightOption>();
  const byInputId = new Map<number, HighlightOption>();
  const stageItemNames = new Map<number, string>();

  for (const stage of stages) {
    for (const stageItem of stage.stage_items ?? []) {
      if (stageItem.id != null && stageItem.name != null) {
        stageItemNames.set(stageItem.id, stageItem.name);
      }
    }
  }

  for (const stage of stages) {
    for (const stageItem of stage.stage_items ?? []) {
      for (const input of stageItem.inputs ?? []) {
        if (input.team_id != null) {
          if (byTeamId.has(input.team_id)) continue;
          const label = input.team?.name ?? `Team ${input.team_id}`;
          byTeamId.set(input.team_id, {
            value: `team:${input.team_id}`,
            label,
            target: { kind: 'team', teamId: input.team_id, label },
          });
          continue;
        }

        if (
          input.id == null ||
          input.winner_from_stage_item_id == null ||
          input.winner_position == null ||
          byInputId.has(input.id)
        ) {
          continue;
        }
        const sourceName =
          stageItemNames.get(input.winner_from_stage_item_id) ??
          `Stage item ${input.winner_from_stage_item_id}`;
        const label = `${positionName(input.winner_position)} of ${sourceName}`;
        byInputId.set(input.id, {
          value: `input:${input.id}`,
          label,
          target: { kind: 'stage-item-input', inputId: input.id, label },
        });
      }
    }
  }

  const byLabel = (a: HighlightOption, b: HighlightOption) => a.label.localeCompare(b.label);
  // Teams first, then placeholder inputs ("1st of group A"), each sorted alphabetically.
  // Actual teams are what users usually want to find, so they take precedence.
  return [...[...byTeamId.values()].sort(byLabel), ...[...byInputId.values()].sort(byLabel)];
}

function positionName(position: number): string {
  return (
    {
      1: '1st',
      2: '2nd',
      3: '3rd',
    }[position] ?? `${position}th`
  );
}
