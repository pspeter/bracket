import type { GridMatchRef } from './selection';

export type MoveSubject = Pick<GridMatchRef, 'played' | 'locked'>;

export type MoveDestination = { kind: 'free-slot' } | { kind: 'swap'; match: MoveSubject };

export function needsMoveConfirmation(moved: MoveSubject, destination: MoveDestination): boolean {
  if (moved.played === true) return true;

  if (destination.kind === 'swap') {
    return (
      moved.locked === true ||
      destination.match.locked === true ||
      destination.match.played === true
    );
  }

  return false;
}
