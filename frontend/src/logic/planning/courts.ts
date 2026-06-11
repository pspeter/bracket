/**
 * Pure, headless helpers for court management on the planning view.
 *
 * The delete-court UI shows how many matches are assigned to each court so the
 * organizer can see up front which deletions the backend will reject (the courts
 * endpoint refuses to delete a court that is used by any match).
 */

export interface CourtManagementEntry<C> {
  court: C;
  matchCount: number;
}

export function buildCourtManagementList<C extends { id: number }, M>(
  courts: C[],
  matchesByCourtId: Record<number, M[]>
): CourtManagementEntry<C>[] {
  return courts.map((court) => ({
    court,
    matchCount: matchesByCourtId[court.id]?.length ?? 0,
  }));
}
