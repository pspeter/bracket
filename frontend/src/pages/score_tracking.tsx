import {
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Flex,
  Grid,
  Container,
  Group,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { Time } from '@components/utils/datetime';
import PreloadLink from '@components/utils/link';
import { formatMatchInput1, formatMatchInput2, getScoreColors } from '@components/utils/match';
import { responseIsValid } from '@components/utils/util';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { getScoreTrackingInfo } from '@services/score_tracking';

function getMatchStateColor(state: string) {
  if (state === 'IN_PROGRESS') return 'blue';
  if (state === 'COMPLETED') return 'green';
  return 'gray';
}

export default function ScoreTrackingPage() {
  const { t } = useTranslation();
  const { score_tracking_token } = useParams<{ score_tracking_token: string }>();
  const swrResponse = getScoreTrackingInfo(score_tracking_token ?? null);

  if (!responseIsValid(swrResponse)) {
    if (swrResponse.error != null) {
      return (
        <Container size="sm" py="xl">
          <Alert color="red">{t('score_tracking_invalid_link')}</Alert>
        </Container>
      );
    }
    return null;
  }

  const info = swrResponse.data.data;
  const matches = info.matches || [];
  const pseudoStagesResponse = {
    data: {
      data: [
        {
          stage_items: [
            {
              id: -1,
              name: '',
              rounds: [{ matches }],
              inputs: [],
            },
          ],
        },
      ],
    },
  };
  const stageItemsLookup = getStageItemLookup(pseudoStagesResponse as any);
  const matchesLookup = getMatchLookup(pseudoStagesResponse as any);

  return (
    <Container size="md" py="xl">
      <Stack>
        <Title order={2}>
          {t('score_tracking_page_title', { tournamentName: info.tournament_name })}
        </Title>
        {matches.length < 1 ? <Alert color="gray">{t('no_matches_title')}</Alert> : null}
        {matches.map((match: any) => (
          <Card key={match.id} withBorder radius="md">
            <Stack gap="xs">
              <Group justify="space-between">
                <Group gap="xs">
                  <Text fw={700}>{match.court?.name || t('none')}</Text>
                  <Badge color={getMatchStateColor(match.state)} variant="light">
                    {t(`match_state_${String(match.state).toLowerCase()}`)}
                  </Badge>
                </Group>
                <Group gap="xs">
                  {match.start_time != null ? (
                    <Badge variant="light">
                      <Time datetime={match.start_time} />
                    </Badge>
                  ) : null}
                </Group>
              </Group>
              <Grid>
                <Grid.Col span="auto" pb="0rem">
                  <Text fw={500}>{formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}</Text>
                </Grid.Col>
                <Grid.Col span="content" pb="0rem">
                  <div
                    style={{
                      backgroundColor: getScoreColors(match).stage_item_input1_score,
                      borderRadius: '0.5rem',
                      width: '2.5rem',
                      color: getScoreColors(match).textColor,
                      fontWeight: 800,
                    }}
                  >
                    <Center>{match.stage_item_input1_score}</Center>
                  </div>
                </Grid.Col>
              </Grid>
              <Grid>
                <Grid.Col span="auto" pb="0rem">
                  <Text fw={500}>{formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}</Text>
                </Grid.Col>
                <Grid.Col span="content" pb="0rem">
                  <div
                    style={{
                      backgroundColor: getScoreColors(match).stage_item_input2_score,
                      borderRadius: '0.5rem',
                      width: '2.5rem',
                      color: getScoreColors(match).textColor,
                      fontWeight: 800,
                    }}
                  >
                    <Center>{match.stage_item_input2_score}</Center>
                  </div>
                </Grid.Col>
              </Grid>
              <Flex justify="center" pt="xs">
              <Button
                component={PreloadLink}
                href={`/score-tracking/${score_tracking_token}/matches/${match.id}`}
              >
                {t('open_score_tracker_button')}
              </Button>
              </Flex>
            </Stack>
          </Card>
        ))}
      </Stack>
    </Container>
  );
}
