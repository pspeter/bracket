export function shouldShowSideSwitchReminder(combinedScore: number, n: number | null): boolean {
  if (n === null || combinedScore === 0) return false;
  return combinedScore % n === 0;
}

export interface SideSwitchState {
  showReminder: boolean;
  dismissedThreshold: number | null;
}

/**
 * Pure transition function: given the new combined score, the previous combined score,
 * the configured threshold n, whether the user just clicked "Switch sides", and the
 * currently dismissed threshold — returns the next SideSwitchState.
 */
export function computeSideSwitchState(
  newCombined: number,
  prevCombined: number,
  n: number | null,
  justDismissed: boolean,
  dismissedThreshold: number | null
): SideSwitchState {
  if (justDismissed) {
    return { showReminder: false, dismissedThreshold: newCombined };
  }

  // If the score moved past a threshold we dismissed, clear the dismissal.
  const clearedDismissal =
    dismissedThreshold !== null && newCombined > dismissedThreshold ? null : dismissedThreshold;

  // Only trigger on an upward transition across a threshold boundary.
  const crossedNewThreshold =
    n !== null &&
    newCombined > 0 &&
    newCombined % n === 0 &&
    newCombined > prevCombined &&
    clearedDismissal !== newCombined;

  return {
    showReminder: crossedNewThreshold,
    dismissedThreshold: clearedDismissal,
  };
}
