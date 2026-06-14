import { describe, expect, it } from 'vitest';

import { needsMoveConfirmation } from './move_confirmation';
import { GridMatchRef } from './selection';

function match(overrides: Partial<GridMatchRef> = {}): GridMatchRef {
  return { matchId: 10, courtId: 1, position: 0, ...overrides };
}

describe('needsMoveConfirmation', () => {
  it('confirms moving a played match to a free slot', () => {
    expect(
      needsMoveConfirmation(match({ played: true }), {
        kind: 'free-slot',
      })
    ).toBe(true);
  });

  it('confirms swapping onto a locked target match', () => {
    expect(
      needsMoveConfirmation(match(), {
        kind: 'swap',
        match: match({ matchId: 20, courtId: 2, locked: true }),
      })
    ).toBe(true);
  });

  it('confirms swapping a locked source match because the target enters the frozen region', () => {
    expect(
      needsMoveConfirmation(match({ locked: true }), {
        kind: 'swap',
        match: match({ matchId: 20, courtId: 2 }),
      })
    ).toBe(true);
  });

  it('does not confirm moving a not-started positionally locked match to free time', () => {
    expect(
      needsMoveConfirmation(match({ locked: true, played: false }), {
        kind: 'free-slot',
      })
    ).toBe(false);
  });

  it('does not confirm a normal free-to-free move', () => {
    expect(
      needsMoveConfirmation(match(), {
        kind: 'free-slot',
      })
    ).toBe(false);
  });
});
