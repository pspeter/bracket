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
import { IconArrowsExchange, IconClock, IconMinus, IconPlus } from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { LevelBadge, LevelFilterSelect } from '@components/levels/levels';
import { formatTimeRange, Time } from '@components/utils/datetime';
import PreloadLink from '@components/utils/link';
import {
  formatMatchInput1,
  formatMatchInput2,
  getMatchScore1,
  getMatchScore2,
} from '@components/utils/match';
import { RefereeDisplay } from '@components/utils/referee';
import { responseIsValid } from '@components/utils/util';
import { getScoreColors } from '@logic/colors';
import {
  getDisplayScores,
  getScoreTrackingViewState,
  isEndSetDisabled,
  nextScoresAfterAdjust,
} from '@logic/score_tracking';
import { computeSideSwitchState } from '@logic/side_switch';
import {
  LevelResponse,
  MatchSet,
  MatchWithDetails,
  ScoreTrackingInfoResponse,
  ScoreTrackingMatchResponse,
} from '@openapi';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { getSetScoreColors } from '../../utils/match_sets';

function getMatchStateColor(state: string) {
  if (state === 'IN_PROGRESS') return 'blue';
  if (state === 'COMPLETED') return 'green';
  return 'gray';
}

// Per-set score chips, mirroring the schedule rows and bracket cards. Multi-set matches show each
// set's score separately; single-set matches keep the single aggregate box.
function SetScoreChip({ set, side }: { set: MatchSet; side: 's1' | 's2' }) {
  const { s1, s2 } = getSetScoreColors(set);
  const bg = side === 's1' ? s1 : s2;
  const value = side === 's1' ? set.stage_item_input1_score : set.stage_item_input2_score;
  const maxScore = Math.max(set.stage_item_input1_score, set.stage_item_input2_score);
  const minWidth = maxScore >= 100 ? '2.8rem' : maxScore >= 10 ? '1.8rem' : '1.5rem';
  return (
    <div
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
}

function MatchSetScores({
  match,
  side,
  aggregateColor,
  aggregateScore,
  aggregateTextColor,
}: {
  match: MatchWithDetails;
  side: 's1' | 's2';
  aggregateColor: string;
  aggregateScore: number;
  aggregateTextColor: string;
}) {
  const isMultiSet = match.num_sets > 1 && match.match_sets.length > 0;
  if (isMultiSet) {
    return (
      <div style={{ display: 'flex', gap: '3px', justifyContent: 'flex-end' }}>
        {match.match_sets.map((set) => (
          <SetScoreChip key={set.id} set={set} side={side} />
        ))}
      </div>
    );
  }
  return (
    <div
      style={{
        backgroundColor: aggregateColor,
        borderRadius: '0.5rem',
        width: '2.5rem',
        color: aggregateTextColor,
        fontWeight: 800,
      }}
    >
      <Center>{aggregateScore}</Center>
    </div>
  );
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
                  <MatchSetScores
                    match={match}
                    side="s1"
                    aggregateColor={getScoreColors(match).stage_item_input1_score}
                    aggregateScore={getMatchScore1(match)}
                    aggregateTextColor={getScoreColors(match).textColor}
                  />
                </Grid.Col>
              </Grid>
              <Grid>
                <Grid.Col span="auto" pb="0rem">
                  <Text fw={500}>
                    {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
                  </Text>
                </Grid.Col>
                <Grid.Col span="content" pb="0rem">
                  <MatchSetScores
                    match={match}
                    side="s2"
                    aggregateColor={getScoreColors(match).stage_item_input2_score}
                    aggregateScore={getMatchScore2(match)}
                    aggregateTextColor={getScoreColors(match).textColor}
                  />
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

function countSetsWon(sets: MatchSet[], slot: 1 | 2): number {
  return sets.filter((s) => {
    if (s.state !== 'COMPLETED') return false;
    if (slot === 1) return s.stage_item_input1_score > s.stage_item_input2_score;
    return s.stage_item_input2_score > s.stage_item_input1_score;
  }).length;
}

export type ScoreTrackingMatchActions = {
  startMatch: () => Promise<void>;
  endMatch: () => Promise<void>;
  reopenMatch: () => Promise<void>;
  scoreEdit: (
    setId: number,
    body: { stage_item_input1_score: number; stage_item_input2_score: number }
  ) => Promise<void>;
};

export function ScoreTrackingMatchView({
  swrResponse,
  nextMatchHref,
  storageKey,
  actions,
  levels = [],
  refereesEnabled = false,
}: {
  swrResponse: SWRResponse<ScoreTrackingMatchResponse>;
  nextMatchHref?: string | null;
  storageKey: string;
  levels?: LevelResponse[];
  refereesEnabled?: boolean;
  actions: ScoreTrackingMatchActions;
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
  const prevSetNumberRef = useRef<number | null>(null);

  const matchData = responseIsValid(swrResponse) ? swrResponse.data!.data : null;
  const n = matchData?.side_switch_every_n_points ?? null;

  const viewState = matchData ? getScoreTrackingViewState(matchData.match_sets) : null;
  const activeSet = viewState?.kind === 'playing' ? viewState.set : null;
  const combinedScore = activeSet
    ? activeSet.stage_item_input1_score + activeSet.stage_item_input2_score
    : 0;

  useEffect(() => {
    if (matchData === null || viewState === null) return;

    // Reset side-switch state when active set changes.
    const currentSetNumber = activeSet?.set_number ?? null;
    if (prevSetNumberRef.current !== null && prevSetNumberRef.current !== currentSetNumber) {
      setShowSideSwitchReminder(false);
      setDismissedThreshold(null);
      prevCombinedRef.current = combinedScore;
      prevSetNumberRef.current = currentSetNumber;
      return;
    }
    prevSetNumberRef.current = currentSetNumber;

    const prev = prevCombinedRef.current;
    if (prev === null) {
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
  }, [combinedScore, matchData]);

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
    },
    {
      slot: 2 as const,
      name: formatMatchInput2(t, stageItemsLookup, matchesLookup, match),
    },
  ];
  const displayedTeams = isSwapped ? [teams[1], teams[0]] : teams;

  async function runAction(action: () => Promise<void>) {
    setIsSaving(true);
    await action();
    await swrResponse.mutate();
    setIsSaving(false);
  }

  async function adjustScore(slot: 1 | 2, delta: number) {
    if (activeSet == null) return;
    await runAction(() =>
      actions.scoreEdit(activeSet.id, nextScoresAfterAdjust(activeSet, slot, delta))
    );
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

  const numSets = match.num_sets;
  const isMultiSet = numSets > 1;

  function renderNotStarted() {
    return (
      <Stack align="center" gap="lg">
        <Group gap="sm" justify="center" wrap="nowrap">
          <Text ta="center" fw={700} fz="lg">
            {displayedTeams[0].name}
          </Text>
          <Text c="dimmed" fw={500}>
            {t('versus_label')}
          </Text>
          <Text ta="center" fw={700} fz="lg">
            {displayedTeams[1].name}
          </Text>
        </Group>
        {match.start_time != null ? (
          <Group gap={6} justify="center">
            <IconClock size={18} color="var(--mantine-color-dimmed)" />
            <Text fw={500} c="dimmed">
              {formatTimeRange(match.start_time, match.duration_minutes)}
            </Text>
          </Group>
        ) : null}
        <Button size="xl" loading={isSaving} onClick={() => runAction(actions.startMatch)}>
          {t('start_game_button')}
        </Button>
      </Stack>
    );
  }

  function renderCompleted() {
    return (
      <Stack gap="sm" align="center">
        <Button size="lg" loading={isSaving} onClick={() => runAction(actions.reopenMatch)}>
          {t('resume_match_button')}
        </Button>
        {nextMatchHref != null ? (
          <Button
            component={PreloadLink}
            href={nextMatchHref}
            size="lg"
            color="blue"
            variant="light"
          >
            {t('next_match_button')}
          </Button>
        ) : null}
      </Stack>
    );
  }

  function renderPlaying(set: MatchSet) {
    const isLastSet = set.set_number === numSets;
    const endDisabled = isSaving || isEndSetDisabled(set, match, isSwapped);

    const { first, second } = getDisplayScores(set, isSwapped);
    const teamDisplayScores = [first, second];

    return (
      <>
        {isMultiSet ? (
          <Center>
            <Text fw={700} fz="lg">
              {t('set_number_label', { current: set.set_number, total: numSets })}
            </Text>
          </Center>
        ) : null}
        <Stack align="center" gap={4}>
          <Button
            variant={showSideSwitchReminder ? 'filled' : 'light'}
            color={showSideSwitchReminder ? 'red' : undefined}
            leftSection={<IconArrowsExchange size={18} />}
            onClick={toggleSides}
          >
            {t('switch_sides_button')}
          </Button>
          <Text
            fz="sm"
            c="red"
            style={{ visibility: showSideSwitchReminder ? 'visible' : 'hidden' }}
          >
            {t('side_switch_reminder_description')}
          </Text>
        </Stack>
        <Grid>
          {displayedTeams.map((team, idx) => (
            <Grid.Col span={6} key={team.slot}>
              <Card withBorder radius="md" p="lg">
                <Stack align="center">
                  <Text ta="center" fw={700}>
                    {team.name}
                  </Text>
                  <Text fz={64} fw={900}>
                    {teamDisplayScores[idx]}
                  </Text>
                  <Group>
                    <ActionIcon
                      size="xl"
                      variant="light"
                      disabled={isSaving}
                      onClick={() => adjustScore(team.slot, -1)}
                    >
                      <IconMinus size={22} />
                    </ActionIcon>
                    <ActionIcon
                      size="xl"
                      variant="filled"
                      disabled={isSaving}
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
          {isLastSet ? (
            <Button
              size="lg"
              color="green"
              loading={isSaving}
              disabled={endDisabled}
              onClick={() => runAction(actions.endMatch)}
            >
              {t('finish_match_button')}
            </Button>
          ) : (
            <Button
              size="lg"
              color="blue"
              loading={isSaving}
              disabled={endDisabled}
              onClick={() => runAction(actions.endMatch)}
            >
              {t('end_set_label')}
            </Button>
          )}
        </Center>
      </>
    );
  }

  function renderBetweenSets(completed: MatchSet, _next: MatchSet, allSets: MatchSet[]) {
    const { first: displayScore1, second: displayScore2 } = getDisplayScores(completed, isSwapped);

    const setsWon1 = isSwapped ? countSetsWon(allSets, 2) : countSetsWon(allSets, 1);
    const setsWon2 = isSwapped ? countSetsWon(allSets, 1) : countSetsWon(allSets, 2);

    return (
      <>
        <Stack align="center" gap="xs">
          <Text fw={700} fz="lg">
            {t('set_number_label', { current: completed.set_number, total: numSets })}
          </Text>
          <Group gap="xl" justify="center">
            {displayedTeams.map((team, idx) => (
              <Stack key={team.slot} align="center" gap={0}>
                <Text ta="center" fw={700}>
                  {team.name}
                </Text>
                <Text fz={64} fw={900}>
                  {idx === 0 ? displayScore1 : displayScore2}
                </Text>
              </Stack>
            ))}
          </Group>
          <Text fz="xl" fw={700}>
            {setsWon1} – {setsWon2}
          </Text>
        </Stack>
        <Stack gap="sm" align="center">
          <Button size="lg" loading={isSaving} onClick={() => runAction(actions.startMatch)}>
            {t('start_next_set_label')}
          </Button>
          <Button
            size="lg"
            variant="light"
            loading={isSaving}
            onClick={() => runAction(actions.reopenMatch)}
          >
            {t('continue_previous_set_label')}
          </Button>
        </Stack>
      </>
    );
  }

  function renderMatchBody() {
    if (viewState == null) return null;
    if (viewState.kind === 'not_started') return renderNotStarted();
    if (viewState.kind === 'completed') {
      return (
        <>
          <Stack align="center" gap={4}>
            <Button
              variant="light"
              leftSection={<IconArrowsExchange size={18} />}
              onClick={toggleSides}
            >
              {t('switch_sides_button')}
            </Button>
          </Stack>
          {renderCompleted()}
        </>
      );
    }
    if (viewState.kind === 'between_sets') {
      return renderBetweenSets(viewState.completed, viewState.next, viewState.allSets);
    }
    // playing
    return renderPlaying(viewState.set);
  }

  return (
    <Container size="sm" py="xl">
      <Stack gap="lg">
        <Group gap="xs">
          <Title order={2}>{t('score_tracking_match_title')}</Title>
          <LevelBadge levels={levels} levelId={match.level_id} />
        </Group>
        <RefereeDisplay match={match} refereesEnabled={refereesEnabled} />
        {renderMatchBody()}
      </Stack>
    </Container>
  );
}
