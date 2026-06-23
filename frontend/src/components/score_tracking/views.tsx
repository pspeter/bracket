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
  Select,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconArrowsExchange, IconMinus, IconPlus } from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { LevelBadge, LevelFilterSelect } from '@components/levels/levels';
import { Time } from '@components/utils/datetime';
import PreloadLink from '@components/utils/link';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { RefereeDisplay } from '@components/utils/referee';
import { responseIsValid } from '@components/utils/util';
import { getScoreColors } from '@logic/colors';
import { computeSideSwitchState } from '@logic/side_switch';
import {
  LevelResponse,
  MatchWithDetails,
  ScoreTrackingInfoResponse,
  ScoreTrackingMatchResponse,
} from '@openapi';
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
  stagesHref,
  courtId,
  onCourtIdChange,
}: {
  swrResponse: SWRResponse<ScoreTrackingInfoResponse>;
  getMatchHref: (matchId: number) => string;
  stagesHref?: string;
  courtId?: number | null;
  onCourtIdChange?: (next: number | null) => void;
}) {
  const { t } = useTranslation();
  const [filteredLevelId, setFilteredLevelId] = useState('all');

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
  const levels = info.levels ?? [];
  const courts = info.courts ?? [];
  const refereesEnabled = info.referees_enabled ?? false;
  const matches = (info.matches || []).filter(
    (match) => filteredLevelId === 'all' || `${match.level_id}` === filteredLevelId
  );
  const courtSelectValue = courtId == null ? 'all' : `${courtId}`;
  const pseudoStagesResponse = getPseudoStagesResponse(matches);
  const stageItemsLookup = getStageItemLookup(pseudoStagesResponse as any);
  const matchesLookup = getMatchLookup(pseudoStagesResponse as any);

  function renderEmptyState() {
    if (matches.length > 0) return null;
    if (!info.has_active_stage) {
      return (
        <Alert color="yellow" title={t('no_active_stage_title')}>
          <Stack gap="xs">
            <Text>{t('no_active_stage_description')}</Text>
            {stagesHref != null ? (
              <Button
                component={PreloadLink}
                href={stagesHref}
                variant="light"
                color="yellow"
                size="xs"
              >
                {t('no_active_stage_go_to_stages')}
              </Button>
            ) : null}
          </Stack>
        </Alert>
      );
    }
    return <Alert color="gray">{t('no_matches_title')}</Alert>;
  }

  return (
    <Container size="md" py="xl">
      <Stack>
        <Title order={2}>
          {t('score_tracking_page_title', { tournamentName: info.tournament_name })}
        </Title>
        <LevelFilterSelect
          levels={levels}
          value={filteredLevelId}
          onChange={setFilteredLevelId}
          label={t('filter_level_label')}
          placeholder={t('filter_level_placeholder')}
          allLevelsLabel={t('all_levels_label')}
        />
        {onCourtIdChange != null && courts.length > 0 ? (
          <Select
            label={t('filter_court_label')}
            placeholder={t('filter_court_placeholder')}
            value={courtSelectValue}
            data={[
              { value: 'all', label: t('all_courts_label') },
              ...courts.map((court) => ({ value: `${court.id}`, label: court.name })),
            ]}
            onChange={(next) => {
              if (next == null || next === 'all') {
                onCourtIdChange(null);
              } else {
                onCourtIdChange(Number(next));
              }
            }}
          />
        ) : null}
        {renderEmptyState()}
        {matches.map((match) => (
          <Card key={match.id} withBorder radius="md">
            <Stack gap="xs">
              <Group justify="space-between">
                <Group gap="xs">
                  <Text fw={700}>{match.court?.name || t('none')}</Text>
                  <Badge color={getMatchStateColor(match.state)} variant="light">
                    {t(`match_state_${String(match.state).toLowerCase()}`)}
                  </Badge>
                  <LevelBadge levels={levels} levelId={match.level_id} />
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
              <RefereeDisplay match={match} refereesEnabled={refereesEnabled} />
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
  levels = [],
  refereesEnabled = false,
}: {
  swrResponse: SWRResponse<ScoreTrackingMatchResponse>;
  backHref: string;
  storageKey: string;
  levels?: LevelResponse[];
  refereesEnabled?: boolean;
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

  const [showSideSwitchReminder, setShowSideSwitchReminder] = useState(false);
  const [dismissedThreshold, setDismissedThreshold] = useState<number | null>(null);
  const prevCombinedRef = useRef<number | null>(null);

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
  const n = match.side_switch_every_n_points ?? null;
  const combinedScore = match.stage_item_input1_score + match.stage_item_input2_score;

  // eslint-disable-next-line react-hooks/rules-of-hooks
  useEffect(() => {
    const prev = prevCombinedRef.current;
    if (prev === null) {
      // On first load: show reminder if currently at a threshold (page reload safety net).
      if (n !== null && combinedScore > 0 && combinedScore % n === 0) {
        setShowSideSwitchReminder(true);
      }
      prevCombinedRef.current = combinedScore;
      return;
    }
    const next = computeSideSwitchState(combinedScore, prev, n, false, dismissedThreshold);
    setShowSideSwitchReminder(next.showReminder);
    setDismissedThreshold(next.dismissedThreshold);
    prevCombinedRef.current = combinedScore;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combinedScore]);

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
    if (showSideSwitchReminder) {
      setShowSideSwitchReminder(false);
      setDismissedThreshold(combinedScore);
    }
  }

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Group justify="space-between">
          <Group gap="xs">
            <Title order={2}>{t('score_tracking_match_title')}</Title>
            <LevelBadge levels={levels} levelId={match.level_id} />
          </Group>
          <Button component={PreloadLink} href={backHref} variant="subtle">
            {t('back_to_matches_button')}
          </Button>
        </Group>
        <RefereeDisplay match={match} refereesEnabled={refereesEnabled} />
        {showSideSwitchReminder && (
          <Alert color="orange" title={t('side_switch_reminder_title')}>
            {t('side_switch_reminder_description')}
          </Alert>
        )}
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
                variant={showSideSwitchReminder ? 'filled' : 'light'}
                color={showSideSwitchReminder ? 'orange' : undefined}
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
