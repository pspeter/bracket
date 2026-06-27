export function formatDifference(value: number): string {
  return value >= 0 ? `+${value}` : `${value}`;
}
