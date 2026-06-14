import { describe, expect, it } from 'vitest';

import { HighlightTarget, matchInvolvesHighlight, stageHighlightOptions } from './highlight';

interface TestInput {
  id: number;
  team_id: number | null;
  team?: { id: number; name: string };
  winner_from_stage_item_id: number | null;
  winner_position: number | null;
}

function input(id: number, teamId: number | null, name?: string): TestInput {
  return {
    id,
    team_id: teamId,
    team: teamId == null ? undefined : { id: teamId, name: name ?? `Team ${teamId}` },
    winner_from_stage_item_id: null,
    winner_position: null,
  };
}

function match(
  id: number,
  input1: ReturnType<typeof input> | null,
  input2: ReturnType<typeof input> | null,
  winnerFromMatch1: number | null = null,
  winnerFromMatch2: number | null = null
) {
  return {
    id,
    stage_item_input1: input1,
    stage_item_input2: input2,
    stage_item_input1_winner_from_match_id: winnerFromMatch1,
    stage_item_input2_winner_from_match_id: winnerFromMatch2,
  };
}

describe('matchInvolvesHighlight', () => {
  const target: HighlightTarget = { kind: 'team', teamId: 11, label: 'Alpha' };

  it('matches direct stage item inputs for the selected team', () => {
    const directMatch = match(1, input(101, 11, 'Alpha'), input(102, 12, 'Beta'));
    const otherMatch = match(2, input(201, 13, 'Gamma'), input(202, 12, 'Beta'));

    expect(matchInvolvesHighlight(directMatch, target, {})).toBe(true);
    expect(matchInvolvesHighlight(otherMatch, target, {})).toBe(false);
  });

  it('matches winner placeholders once the source match resolves to the selected team', () => {
    const source = match(1, input(101, 11, 'Alpha'), input(102, 12, 'Beta'));
    const unresolvedFinal = match(2, null, input(203, 13, 'Gamma'), 1);

    expect(
      matchInvolvesHighlight(unresolvedFinal, target, {
        1: { match: source },
      })
    ).toBe(true);
  });

  it('matches selected stage item inputs and inherited winner placeholders', () => {
    const inputTarget: HighlightTarget = {
      kind: 'stage-item-input',
      inputId: 301,
      label: '1st of Group A',
    };
    const source = match(1, { ...input(301, null), winner_from_stage_item_id: 10 }, input(302, 12));
    const final = match(2, null, input(203, 13, 'Gamma'), 1);

    expect(matchInvolvesHighlight(source, inputTarget, {})).toBe(true);
    expect(matchInvolvesHighlight(final, inputTarget, { 1: { match: source } })).toBe(true);
  });
});

describe('stageHighlightOptions', () => {
  it('lists searchable teams from stage item inputs without duplicates', () => {
    expect(
      stageHighlightOptions([
        {
          stage_items: [
            {
              inputs: [
                input(101, 11, 'Alpha'),
                input(102, 12, 'Beta'),
                input(103, 11, 'Alpha'),
                input(104, null),
              ],
            },
          ],
        },
      ])
    ).toEqual([
      { value: 'team:11', label: 'Alpha', target: { kind: 'team', teamId: 11, label: 'Alpha' } },
      { value: 'team:12', label: 'Beta', target: { kind: 'team', teamId: 12, label: 'Beta' } },
    ]);
  });

  it('lists tentative stage item inputs as searchable options', () => {
    expect(
      stageHighlightOptions([
        {
          stage_items: [
            { id: 10, name: 'Group A', inputs: [] },
            {
              id: 20,
              name: 'Final',
              inputs: [{ ...input(301, null), winner_from_stage_item_id: 10, winner_position: 1 }],
            },
          ],
        },
      ])
    ).toEqual([
      {
        value: 'input:301',
        label: '1st of Group A',
        target: { kind: 'stage-item-input', inputId: 301, label: '1st of Group A' },
      },
    ]);
  });

  it('lists teams before placeholder inputs, each sorted alphabetically', () => {
    expect(
      stageHighlightOptions([
        {
          stage_items: [
            { id: 10, name: 'Group A', inputs: [] },
            { id: 20, name: 'Group B', inputs: [] },
            {
              id: 30,
              name: 'Final',
              inputs: [
                { ...input(301, null), winner_from_stage_item_id: 20, winner_position: 1 },
                { ...input(302, null), winner_from_stage_item_id: 10, winner_position: 1 },
                input(103, 12, 'Zeta'),
                input(104, 11, 'Alpha'),
              ],
            },
          ],
        },
      ]).map((option) => option.label)
    ).toEqual(['Alpha', 'Zeta', '1st of Group A', '1st of Group B']);
  });
});
