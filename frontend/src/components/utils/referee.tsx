import { Flex, Text } from '@mantine/core';
import { GiWhistle } from '@react-icons/all-files/gi/GiWhistle';

import { MatchWithDetails } from '@openapi';
import { formatStageItemInput } from './stage_item_input';

type RefereeFields = Pick<MatchWithDetails, 'referee' | 'referee_name'>;

/**
 * The display name of a match's referee: the free-text name when set, otherwise the referee
 * slot's resolved team name, falling back to its placeholder label ("1st of Group A") when the
 * slot is not resolved yet. `stageItemsLookup` is only needed to render placeholder labels.
 */
export function getRefereeName(match: RefereeFields, stageItemsLookup: any = {}): string | null {
  if (match.referee_name != null) return match.referee_name;
  return formatStageItemInput(match.referee ?? null, stageItemsLookup);
}

export function RefereeDisplay({
  match,
  refereesEnabled,
  stageItemsLookup = {},
}: {
  match: RefereeFields;
  refereesEnabled: boolean;
  stageItemsLookup?: any;
}) {
  const name = getRefereeName(match, stageItemsLookup);
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
