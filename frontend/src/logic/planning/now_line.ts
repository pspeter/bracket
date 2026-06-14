export function currentTimeOffsetMinutes({
  tournamentStartTime,
  totalMinutes,
  now,
}: {
  tournamentStartTime: string | Date;
  totalMinutes: number;
  now: Date;
}): number | null {
  const startTime =
    tournamentStartTime instanceof Date ? tournamentStartTime : new Date(tournamentStartTime);
  const offsetMinutes = (now.getTime() - startTime.getTime()) / 60_000;

  if (offsetMinutes < 0 || offsetMinutes > totalMinutes) return null;
  return offsetMinutes;
}
