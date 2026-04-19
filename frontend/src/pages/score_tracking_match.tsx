import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Center,
  Container,
  Grid,
  Group,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconArrowsExchange, IconMinus, IconPlus } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import PreloadLink from '@components/utils/link';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { responseIsValid } from '@components/utils/util';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { updateScoreTrackingMatch } from '@services/match';
import { getScoreTrackingMatch } from '@services/score_tracking';

function getSideStorageKey(token: string, matchId: number) {
  return `score-tracking:${token}:${matchId}:swapped`;
}

export default function ScoreTrackingMatchPage() {
  const { t } = useTranslation();
  const { score_tracking_token, match_id } = useParams<{
    score_tracking_token: string;
    match_id: string;
  }>();
  const matchId = match_id != null ? parseInt(match_id, 10) : null;
  const swrResponse = getScoreTrackingMatch(score_tracking_token ?? null, matchId);
  const [isSaving, setIsSaving] = useState(false);

  const swapped = useMemo(() => {
    if (typeof window === 'undefined' || score_tracking_token == null || matchId == null)
      return false;
    return window.localStorage.getItem(getSideStorageKey(score_tracking_token, matchId)) === 'true';
  }, [score_tracking_token, matchId]);
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

  const match = swrResponse.data.data;
  const pseudoStagesResponse = {
    data: {
      data: [{ stage_items: [{ id: -1, name: '', rounds: [{ matches: [match] }], inputs: [] }] }],
    },
  };
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

  async function saveMatch(next: {
    stage_item_input1_score: number;
    stage_item_input2_score: number;
    state: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  }) {
    if (score_tracking_token == null || matchId == null) return;
    setIsSaving(true);
    await updateScoreTrackingMatch(score_tracking_token, matchId, next);
    await swrResponse.mutate();
    setIsSaving(false);
  }

  async function adjustScore(slot: 1 | 2, delta: number) {
    const next1 = Math.max(0, match.stage_item_input1_score + (slot === 1 ? delta : 0));
    const next2 = Math.max(0, match.stage_item_input2_score + (slot === 2 ? delta : 0));
    await saveMatch({
      stage_item_input1_score: next1,
      stage_item_input2_score: next2,
      state: 'IN_PROGRESS',
    });
  }

  function toggleSides() {
    const nextValue = !isSwapped;
    setIsSwapped(nextValue);
    if (typeof window !== 'undefined' && score_tracking_token != null && matchId != null) {
      window.localStorage.setItem(getSideStorageKey(score_tracking_token, matchId), `${nextValue}`);
    }
  }

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <Title order={2}>{t('score_tracking_match_title')}</Title>
          <Button
            component={PreloadLink}
            href={`/score-tracking/${score_tracking_token}`}
            variant="subtle"
          >
            {t('back_to_matches_button')}
          </Button>
        </Group>
        {match.state === 'NOT_STARTED' ? (
          <Center>
            <Button
              size="xl"
              loading={isSaving}
              onClick={() =>
                saveMatch({
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
                    saveMatch({
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
                    saveMatch({
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
