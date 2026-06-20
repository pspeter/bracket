import { Center, Group, Text } from '@mantine/core';
import { AiOutlineHourglass } from '@react-icons/all-files/ai/AiOutlineHourglass';
import React from 'react';
import { useTranslation } from 'react-i18next';

import { NoContent } from '@components/no_content/empty_table_info';
import { compareDateTime, formatTime } from '@components/utils/datetime';
import { LevelResponse, MatchWithDetails } from '@openapi';
import { ScheduleRow } from './schedule_row';

export function MatchesList({
  matchesLookup,
  stageItemsLookup,
  levels,
  refereesEnabled,
  onMatchClick,
}: {
  matchesLookup: any;
  stageItemsLookup: any;
  levels: LevelResponse[];
  refereesEnabled: boolean;
  onMatchClick?: (match: MatchWithDetails) => void;
}) {
  const { t } = useTranslation();

  const sortedMatches: any[] = (Object.values(matchesLookup) as any[])
    .filter((item: any) => item.match.start_time != null)
    .sort(
      (m1: any, m2: any) =>
        compareDateTime(m1.match.start_time, m2.match.start_time) ||
        (m1.match.court?.name || '').localeCompare(m2.match.court?.name || '') ||
        m1.match.id - m2.match.id
    );

  const rows: React.JSX.Element[] = [];
  for (let c = 0; c < sortedMatches.length; c += 1) {
    const data = sortedMatches[c];
    const startTime = formatTime(data.match.start_time);

    if (c < 1 || startTime !== formatTime(sortedMatches[c - 1].match.start_time as string)) {
      rows.push(
        <Center mt="md" key={`time-${c}`}>
          <Text size="xl" fw={800}>
            {startTime}
          </Text>
        </Center>
      );
    }

    rows.push(
      <ScheduleRow
        key={data.match.id}
        data={data}
        stageItemsLookup={stageItemsLookup}
        matchesLookup={matchesLookup}
        levels={levels}
        refereesEnabled={refereesEnabled}
        onClick={onMatchClick != null ? () => onMatchClick(data.match) : undefined}
      />
    );
  }

  return (
    <Group wrap="nowrap" align="top" style={{ width: '100%' }}>
      <div style={{ width: '100%' }}>
        {rows.length > 0 ? (
          rows
        ) : (
          <NoContent title={t('no_matches_title')} description="" icon={<AiOutlineHourglass />} />
        )}
      </div>
    </Group>
  );
}
