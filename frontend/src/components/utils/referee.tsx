import { Flex, Text } from '@mantine/core';
import { GiWhistle } from '@react-icons/all-files/gi/GiWhistle';

import { Referee } from '@openapi';

export function getRefereeName(referee: Referee | null | undefined): string | null {
  if (referee == null) return null;
  return referee.name ?? referee.team_name ?? null;
}

export function RefereeDisplay({
  referee,
  refereesEnabled,
}: {
  referee: Referee | null | undefined;
  refereesEnabled: boolean;
}) {
  const name = getRefereeName(referee);
  if (!refereesEnabled || name == null) return null;

  return (
    <Flex gap={4} align="center" wrap="nowrap">
      <GiWhistle size={13} style={{ flexShrink: 0, color: 'var(--mantine-color-dimmed)' }} />
      <Text size="xs" c="dimmed" truncate>
        {name}
      </Text>
    </Flex>
  );
}
