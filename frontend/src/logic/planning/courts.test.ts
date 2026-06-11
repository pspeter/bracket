import { describe, expect, it } from 'vitest';

import { buildCourtManagementList } from './courts';

function court(id: number) {
  return { id, name: `Court ${id}` };
}

function match(id: number) {
  return { id };
}

describe('buildCourtManagementList', () => {
  it('returns one entry per court in order, with zero counts when nothing is assigned', () => {
    const entries = buildCourtManagementList([court(2), court(1)], {});

    expect(entries).toEqual([
      { court: court(2), matchCount: 0 },
      { court: court(1), matchCount: 0 },
    ]);
  });

  it('counts the matches assigned to each court', () => {
    const entries = buildCourtManagementList([court(1), court(2)], {
      1: [match(10), match(11), match(12)],
      2: [match(20)],
    });

    expect(entries).toEqual([
      { court: court(1), matchCount: 3 },
      { court: court(2), matchCount: 1 },
    ]);
  });

  it('ignores match groups for unknown courts (e.g. the null group of unassigned matches)', () => {
    const entries = buildCourtManagementList([court(1)], {
      1: [match(10)],
      null: [match(30)],
      7: [match(40)],
    } as Record<number, { id: number }[]>);

    expect(entries).toEqual([{ court: court(1), matchCount: 1 }]);
  });
});
