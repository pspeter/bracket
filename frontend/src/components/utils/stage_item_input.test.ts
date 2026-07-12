import { describe, expect, it } from 'vitest';

import { StageItemInputEmpty, StageItemInputFinal, StageItemInputTentative, Team } from '@openapi';

import { isEligibleRefereeSlot } from './stage_item_input';

const baseInput = {
  id: 1,
  slot: 0,
  stage_item_id: 1,
  tournament_id: 1,
  points: '0',
  wins: 0,
  draws: 0,
  losses: 0,
  set_difference: 0,
  point_difference: 0,
};

function makeTeam(overrides: Partial<Team>): Team {
  return {
    id: 1,
    tournament_id: 1,
    created: '2026-01-01T00:00:00Z',
    name: 'Team 1',
    active: true,
    elo_score: '0',
    swiss_score: '0',
    wins: 0,
    draws: 0,
    losses: 0,
    logo_path: null,
    level_id: null,
    ...overrides,
  } as Team;
}

function makeFinalInput(active: boolean): StageItemInputFinal {
  return {
    ...baseInput,
    team_id: 1,
    winner_from_stage_item_id: null,
    winner_position: null,
    team: makeTeam({ active }),
  };
}

function makeTentativeInput(): StageItemInputTentative {
  return {
    ...baseInput,
    team_id: null,
    winner_from_stage_item_id: 1,
    winner_position: 1,
  };
}

function makeEmptyInput(): StageItemInputEmpty {
  return {
    ...baseInput,
    team_id: null,
    winner_from_stage_item_id: null,
    winner_position: null,
  };
}

describe('isEligibleRefereeSlot', () => {
  it('excludes a Final slot whose team is inactive', () => {
    expect(isEligibleRefereeSlot(makeFinalInput(false))).toBe(false);
  });

  it('includes a Final slot whose team is active', () => {
    expect(isEligibleRefereeSlot(makeFinalInput(true))).toBe(true);
  });

  it('includes a Tentative slot (team not yet known)', () => {
    expect(isEligibleRefereeSlot(makeTentativeInput())).toBe(true);
  });

  it('includes an Empty slot (team not yet known)', () => {
    expect(isEligibleRefereeSlot(makeEmptyInput())).toBe(true);
  });
});
