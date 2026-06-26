import { Badge, Card, Center, Flex, Grid, Stack, Text, UnstyledButton } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { LevelBadge } from '@components/levels/levels';
import { Time } from '@components/utils/datetime';
import {
  formatMatchInput1,
  formatMatchInput2,
  getMatchScore1,
  getMatchScore2,
} from '@components/utils/match';
import { RefereeDisplay } from '@components/utils/referee';
import { getScoreColors } from '@logic/colors';
import { LevelResponse, MatchSet, MatchWithDetails } from '@openapi';
import { stringToColour } from '@services/lookups';
import { getSetScoreColors, getSetsWon } from '../../utils/match_sets';

export function ScheduleRow({
  data,
  stageItemsLookup,
  matchesLookup,
  levels,
  refereesEnabled,
  onClick,
}: {
  data: any;
  stageItemsLookup: any;
  matchesLookup: any;
  levels: LevelResponse[];
  refereesEnabled: boolean;
  onClick?: () => void;
}) {
  const { t } = useTranslation();
  const match: MatchWithDetails = data.match;
  const isMultiSet = match.num_sets > 1 && match.match_sets.length > 0;
  const { input1: setsWon1, input2: setsWon2 } = getSetsWon(match.match_sets);
  const displayScore1 = isMultiSet ? setsWon1 : getMatchScore1(match);
  const displayScore2 = isMultiSet ? setsWon2 : getMatchScore2(match);

  const scoreSource = isMultiSet
    ? { ...match, stage_item_input1_score: setsWon1, stage_item_input2_score: setsWon2 }
    : match;
  const colors = getScoreColors(scoreSource as MatchWithDetails);

  const setScoreChip = (set: MatchSet, side: 's1' | 's2') => {
    const { s1, s2 } = getSetScoreColors(set);
    const bg = side === 's1' ? s1 : s2;
    const value = side === 's1' ? set.stage_item_input1_score : set.stage_item_input2_score;
    const maxScore = Math.max(set.stage_item_input1_score, set.stage_item_input2_score);
    const minWidth = maxScore >= 100 ? '2.8rem' : maxScore >= 10 ? '2rem' : '1.5rem';
    return (
      <div
        key={set.id}
        style={{
          backgroundColor: bg,
          borderRadius: '0.4rem',
          minWidth,
          color: 'white',
          fontWeight: 800,
          textAlign: 'center',
          padding: '0 4px',
        }}
      >
        {value}
      </div>
    );
  };

  const multiSetScoreCell = (side: 's1' | 's2') => (
    <div style={{ display: 'flex', gap: '3px', justifyContent: 'flex-end' }}>
      {match.match_sets.map((set) => setScoreChip(set, side))}
    </div>
  );

  const card = (
    <Card
      shadow="sm"
      radius="md"
      withBorder
      mt="md"
      pt="0rem"
      onClick={onClick}
      style={onClick != null ? { cursor: 'pointer' } : undefined}
    >
      <Card.Section withBorder>
        <Grid pt="0.75rem" pb="0.5rem">
          <Grid.Col mb="0rem" span={4}>
            <Text pl="sm" mt="sm" fw={800}>
              {data.match.court.name}
            </Text>
          </Grid.Col>
          <Grid.Col mb="0rem" span={3}>
            <Center>
              <Text mt="sm" fw={800}>
                {data.match.start_time != null ? <Time datetime={data.match.start_time} /> : null}
              </Text>
            </Center>
          </Grid.Col>
          <Grid.Col mb="0rem" span={5}>
            <Flex justify="right" align="center" gap="xs" mr="xs" mt="0.8rem">
              <LevelBadge levels={levels} levelId={data.stage.level_id} />
              <Badge color={stringToColour(`${data.stageItem.id}`)} variant="outline" size="md">
                {data.stageItem.name}
              </Badge>
            </Flex>
          </Grid.Col>
        </Grid>
      </Card.Section>
      <Stack pt="sm">
        <Grid>
          <Grid.Col span="auto" pb="0rem">
            <Text fw={500}>
              {formatMatchInput1(t, stageItemsLookup, matchesLookup, data.match)}
            </Text>
          </Grid.Col>
          <Grid.Col span="content" pb="0rem">
            {isMultiSet ? (
              multiSetScoreCell('s1')
            ) : (
              <div
                style={{
                  backgroundColor: colors.stage_item_input1_score,
                  borderRadius: '0.5rem',
                  width: '2.5rem',
                  color: colors.textColor,
                  fontWeight: 800,
                }}
              >
                <Center>{displayScore1}</Center>
              </div>
            )}
          </Grid.Col>
        </Grid>
        <Grid mb="0rem">
          <Grid.Col span="auto" pb="0rem">
            <Text fw={500}>
              {formatMatchInput2(t, stageItemsLookup, matchesLookup, data.match)}
            </Text>
          </Grid.Col>
          <Grid.Col span="content" pb="0rem">
            {isMultiSet ? (
              multiSetScoreCell('s2')
            ) : (
              <div
                style={{
                  backgroundColor: colors.stage_item_input2_score,
                  borderRadius: '0.5rem',
                  width: '2.5rem',
                  color: colors.textColor,
                  fontWeight: 800,
                }}
              >
                <Center>{displayScore2}</Center>
              </div>
            )}
          </Grid.Col>
        </Grid>
        <RefereeDisplay match={data.match} refereesEnabled={refereesEnabled} />
      </Stack>
    </Card>
  );

  if (onClick != null) {
    return <UnstyledButton style={{ width: '100%' }}>{card}</UnstyledButton>;
  }
  return card;
}
