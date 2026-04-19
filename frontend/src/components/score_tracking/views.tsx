import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Container,
  Flex,
  Grid,
  Group,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconArrowsExchange, IconMinus, IconPlus } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { Time } from '@components/utils/datetime';
import PreloadLink from '@components/utils/link';
import { formatMatchInput1, formatMatchInput2, getScoreColors } from '@components/utils/match';
import { responseIsValid } from '@components/utils/util';
import { MatchWithDetails, ScoreTrackingInfoResponse, ScoreTrackingMatchResponse } from '@openapi';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';

function getMatchStateColor(state: string) {
  if (state === 'IN_PROGRESS') return 'blue';
  if (state === 'COMPLETED') return 'green';
  return 'gray';
}

function getPseudoStagesResponse(matches: MatchWithDetails[]) {
  return {
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
}

export function ScoreTrackingListView({
  swrResponse,
  getMatchHref,
}: {
  swrResponse: SWRResponse<ScoreTrackingInfoResponse>;
  getMatchHref: (matchId: number) => string;
}) {
  const { t } = useTranslation();

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

  const responseData = swrResponse.data!;
  const info = responseData.data;
  const matches = info.matches || [];
  const pseudoStagesResponse = getPseudoStagesResponse(matches);
  const stageItemsLookup = getStageItemLookup(pseudoStagesResponse as any);
  const matchesLookup = getMatchLookup(pseudoStagesResponse as any);

  return (
    <Container size="md" py="xl">
      <Stack>
        <Title order={2}>
          {t('score_tracking_page_title', { tournamentName: info.tournament_name })}
        </Title>
        {matches.length < 1 ? <Alert color="gray">{t('no_matches_title')}</Alert> : null}
        {matches.map((match) => (
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
                  <Text fw={500}>
                    {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}
                  </Text>
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
                  <Text fw={500}>
                    {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
                  </Text>
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
                <Button component={PreloadLink} href={getMatchHref(match.id)}>
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

export function ScoreTrackingMatchView({
  swrResponse,
  backHref,
  storageKey,
  saveMatch,
}: {
  swrResponse: SWRResponse<ScoreTrackingMatchResponse>;
  backHref: string;
  storageKey: string;
  saveMatch: (next: {
    stage_item_input1_score: number;
    stage_item_input2_score: number;
    state: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  }) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [isSaving, setIsSaving] = useState(false);

  const swapped = useMemo(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(storageKey) === 'true';
  }, [storageKey]);
  const [isSwapped, setIsSwapped] = useState(swapped);

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

  const responseData = swrResponse.data!;
  const match = responseData.data;
  const pseudoStagesResponse = getPseudoStagesResponse([match]);
  const stageItemsLookup = getStageItemLookup(pseudoStagesResponse as any);
  const matchesLookup = getMatchLookup(pseudoStagesResponse as any);

  const teams = [
    {
      slot: 1 as const,
      name: formatMatchInput1(t, stageItemsLookup, matchesLookup, match),
      score: match.stage_item_input1_score,
    },
    {
      slot: 2 as const,
      name: formatMatchInput2(t, stageItemsLookup, matchesLookup, match),
      score: match.stage_item_input2_score,
    },
  ];
  const displayedTeams = isSwapped ? [teams[1], teams[0]] : teams;

  async function persistMatch(next: {
    stage_item_input1_score: number;
    stage_item_input2_score: number;
    state: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  }) {
    setIsSaving(true);
    await saveMatch(next);
    await swrResponse.mutate();
    setIsSaving(false);
  }

  async function adjustScore(slot: 1 | 2, delta: number) {
    const next1 = Math.max(0, match.stage_item_input1_score + (slot === 1 ? delta : 0));
    const next2 = Math.max(0, match.stage_item_input2_score + (slot === 2 ? delta : 0));
    await persistMatch({
      stage_item_input1_score: next1,
      stage_item_input2_score: next2,
      state: 'IN_PROGRESS',
    });
  }

  function toggleSides() {
    const nextValue = !isSwapped;
    setIsSwapped(nextValue);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, `${nextValue}`);
    }
  }

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <Title order={2}>{t('score_tracking_match_title')}</Title>
          <Button component={PreloadLink} href={backHref} variant="subtle">
            {t('back_to_matches_button')}
          </Button>
        </Group>
        {match.state === 'NOT_STARTED' ? (
          <Center>
            <Button
              size="xl"
              loading={isSaving}
              onClick={() =>
                persistMatch({
                  stage_item_input1_score: match.stage_item_input1_score,
                  stage_item_input2_score: match.stage_item_input2_score,
                  state: 'IN_PROGRESS',
                })
              }
            >
              {t('start_game_button')}
            </Button>
          </Center>
        ) : (
          <>
            <Group justify="center">
              <Button
                variant="light"
                leftSection={<IconArrowsExchange size={18} />}
                onClick={toggleSides}
              >
                {t('switch_sides_button')}
              </Button>
            </Group>
            <Grid>
              {displayedTeams.map((team) => (
                <Grid.Col span={6} key={team.slot}>
                  <Card withBorder radius="md" p="lg">
                    <Stack align="center">
                      <Text ta="center" fw={700}>
                        {team.name}
                      </Text>
                      <Text fz={64} fw={900}>
                        {team.score}
                      </Text>
                      <Group>
                        <ActionIcon
                          size="xl"
                          variant="light"
                          disabled={isSaving || match.state !== 'IN_PROGRESS'}
                          onClick={() => adjustScore(team.slot, -1)}
                        >
                          <IconMinus size={22} />
                        </ActionIcon>
                        <ActionIcon
                          size="xl"
                          variant="filled"
                          disabled={isSaving || match.state !== 'IN_PROGRESS'}
                          onClick={() => adjustScore(team.slot, 1)}
                        >
                          <IconPlus size={22} />
                        </ActionIcon>
                      </Group>
                    </Stack>
                  </Card>
                </Grid.Col>
              ))}
            </Grid>
            <Center>
              {match.state === 'COMPLETED' ? (
                <Button
                  size="lg"
                  loading={isSaving}
                  onClick={() =>
                    persistMatch({
                      stage_item_input1_score: match.stage_item_input1_score,
                      stage_item_input2_score: match.stage_item_input2_score,
                      state: 'IN_PROGRESS',
                    })
                  }
                >
                  {t('resume_match_button')}
                </Button>
              ) : (
                <Button
                  size="lg"
                  color="green"
                  loading={isSaving}
                  onClick={() =>
                    persistMatch({
                      stage_item_input1_score: match.stage_item_input1_score,
                      stage_item_input2_score: match.stage_item_input2_score,
                      state: 'COMPLETED',
                    })
                  }
                >
                  {t('finish_match_button')}
                </Button>
              )}
            </Center>
          </>
        )}
      </Stack>
    </Container>
  );
}
