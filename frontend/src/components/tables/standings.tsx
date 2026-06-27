import { Table, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { PlayerScore } from '@components/info/player_score';
import { EmptyTableInfo } from '@components/no_content/empty_table_info';
import { formatStageItemInput } from '@components/utils/stage_item_input';
import { formatDifference } from '@logic/standings';
import { Ranking, StageItemInputFinal, StageItemWithRounds } from '@openapi';
import { ThNotSortable, ThSortable, getTableState } from './table';
import TableLayoutLarge from './table_large';

export function StandingsTableForStageItem({
  teams_with_inputs,
  stageItem,
  fontSizeInPixels,
  stageItemsLookup,
  maxTeamsToDisplay,
  ranking,
}: {
  teams_with_inputs: StageItemInputFinal[];
  stageItem: StageItemWithRounds;
  fontSizeInPixels: number;
  stageItemsLookup: any;
  maxTeamsToDisplay: number;
  ranking?: Ranking | null;
}) {
  const { t } = useTranslation();
  const tableState = getTableState('points', false);

  const minPoints = Math.min(...teams_with_inputs.map((input) => parseFloat(input.points)));
  const maxPoints = Math.max(...teams_with_inputs.map((input) => parseFloat(input.points)));

  // Tied matches only earn points (and are worth showing) when the ranking awards draw points.
  const showTiedColumn = parseFloat(ranking?.match_points?.draw_points ?? '0') !== 0;

  const rows = teams_with_inputs
    .sort((p1: StageItemInputFinal, p2: StageItemInputFinal) => {
      const pts1 = parseFloat(p1.points);
      const pts2 = parseFloat(p2.points);
      if (pts1 !== pts2) return pts2 - pts1;
      const sd1 = p1.set_difference ?? 0;
      const sd2 = p2.set_difference ?? 0;
      if (sd1 !== sd2) return sd2 - sd1;
      const pd1 = p1.point_difference ?? 0;
      const pd2 = p2.point_difference ?? 0;
      return pd2 - pd1;
    })
    .slice(0, maxTeamsToDisplay)
    .map((team_with_input, index) => (
      <Table.Tr key={team_with_input.id}>
        <Table.Td style={{ width: '2rem' }}>{index + 1}</Table.Td>
        <Table.Td style={{ width: '20rem' }}>
          <Text truncate="end" lineClamp={1} inherit>
            {formatStageItemInput(team_with_input, stageItemsLookup)}
          </Text>
        </Table.Td>
        <Table.Td style={{ minWidth: '8rem' }}>
          <Text truncate="end" lineClamp={1} inherit>
            {team_with_input.points}
          </Text>
        </Table.Td>
        {stageItem.type === 'SWISS' ? (
          <Table.Td style={{ minWidth: '10rem' }}>
            <PlayerScore
              score={parseFloat(team_with_input.points)}
              min_score={minPoints}
              max_score={maxPoints}
              decimals={0}
              fontSizeInPixels={fontSizeInPixels}
            />
          </Table.Td>
        ) : (
          <>
            <Table.Td style={{ minWidth: '6rem' }}>
              {(team_with_input.wins ?? 0) +
                (team_with_input.draws ?? 0) +
                (team_with_input.losses ?? 0)}
            </Table.Td>
            <Table.Td style={{ minWidth: '6rem' }}>{team_with_input.wins}</Table.Td>
            {showTiedColumn && (
              <Table.Td style={{ minWidth: '6rem' }}>{team_with_input.draws}</Table.Td>
            )}
            <Table.Td style={{ minWidth: '6rem' }}>
              {formatDifference(team_with_input.set_difference ?? 0)}
            </Table.Td>
            <Table.Td style={{ minWidth: '6rem' }}>
              {formatDifference(team_with_input.point_difference ?? 0)}
            </Table.Td>
          </>
        )}
      </Table.Tr>
    ));

  if (rows.length < 1) return <EmptyTableInfo entity_name={t('teams_title')} />;

  return (
    <TableLayoutLarge display_mode="presentation">
      <Table.Thead>
        <Table.Tr>
          <ThNotSortable>#</ThNotSortable>
          <ThSortable state={tableState} field="name">
            {t('name_table_header')}
          </ThSortable>
          {stageItem.type === 'SWISS' ? (
            <>
              <ThSortable visibleFrom="sm" state={tableState} field="points">
                {t('elo_score')}
              </ThSortable>
              <ThSortable state={tableState} field="elo_score">
                {t('elo_score')}
              </ThSortable>
            </>
          ) : (
            <>
              <ThSortable state={tableState} field="points">
                {t('points_table_header')}
              </ThSortable>
              <ThNotSortable>{t('matches_played_label')}</ThNotSortable>
              <ThNotSortable>{t('matches_won_label')}</ThNotSortable>
              {showTiedColumn && <ThNotSortable>{t('matches_tied_label')}</ThNotSortable>}
              <ThNotSortable>{t('set_difference_label')}</ThNotSortable>
              <ThNotSortable>{t('point_difference_label')}</ThNotSortable>
            </>
          )}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>{rows}</Table.Tbody>
    </TableLayoutLarge>
  );
}
