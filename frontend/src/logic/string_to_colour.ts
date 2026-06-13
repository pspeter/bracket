/**
 * Deterministic Mantine colour for an arbitrary key (team, level, stage item, …),
 * so the same entity is painted the same colour everywhere in the app. Pure and
 * dependency-free, so both the service layer and the logic layer — and their unit
 * tests — can share it as the single source of truth for entity colours.
 */
export function stringToColour(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    // eslint-disable-next-line no-bitwise
    hash = input.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = [
    'pink',
    'violet',
    'green',
    'blue',
    'red',
    'grape',
    'indigo',
    'cyan',
    'orange',
    'yellow',
    'teal',
  ];
  return colors[Math.abs(hash) % colors.length];
}
