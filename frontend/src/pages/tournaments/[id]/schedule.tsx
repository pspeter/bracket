import { DragDropContext, Draggable, Droppable } from '@hello-pangea/dnd';
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Grid,
  Group,
  Menu,
  Paper,
  Stack,
  Text,
  Title,
  alpha,
  useMantineColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { IconAlertCircle, IconCalendarPlus, IconDots, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import CourtModal from '@components/modals/create_court_modal';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { assert_not_none } from '@components/utils/assert';
import { Time } from '@components/utils/datetime';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { TournamentMinimal } from '@components/utils/tournament';
import { Translator } from '@components/utils/types';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { Court, CourtsResponse, MatchWithDetails, StageWithStageItems } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getCourts, getStages } from '@services/adapter';
import { deleteCourt } from '@services/court';
import {
  MatchLookupEntry,
  getMatchLookup,
  getMatchLookupByCourt,
  getScheduleData,
  getStageItemLookup,
  getUnscheduledMatches,
  stringToColour,
} from '@services/lookups';
import { rescheduleMatch, scheduleMatches, unscheduleMatch } from '@services/match';

const UNSCHEDULED_DROPPABLE_ID = 'unscheduled';

const COL_WIDTH = '25rem';

/** @hello-pangea droppable id for the unscheduled lane in a specific stage (multi-stage layout). */
function unschedDroppableIdForStage(stageId: number) {
  return `u-${stageId}`;
}

/** @hello-pangea droppable id for a court's matches within one stage. */
function courtStageDroppableId(courtId: number, stageId: number) {
  return `c-${courtId}-s-${stageId}`;
}

/**
 * Whether a droppable is an unscheduled column: legacy single `unscheduled` or per-stage `u-{id}`.
 */
function isUnschedDroppableId(droppableId: string) {
  return droppableId === UNSCHEDULED_DROPPABLE_ID || droppableId.startsWith('u-');
}

/**
 * Parses a multi-stage court droppable id (`c-{courtId}-s-{stageId}`) or returns null.
 */
function tryParseCourtDroppableId(
  droppableId: string
): { courtId: number; stageId: number } | null {
  const m = droppableId.match(/^c-(\d+)-s-(\d+)$/);
  if (m == null) return null;
  return { courtId: parseInt(m[1], 10), stageId: parseInt(m[2], 10) };
}

/** 0-based index of `stageId` in the tournament’s ordered stage list. */
function stageOrderIndex(stageOrder: StageWithStageItems[], stageId: number) {
  return stageOrder.findIndex((s) => s.id === stageId);
}

/**
 * If the destination stage has no matches on the court yet, return the global insert index
 * in `G` (matches on that court, ex-drag) so the new subsequence is ordered before the first
 * match whose stage comes *after* `destStageId` in `stageOrder`.
 */
function findInsertForEmptyDestStage(
  G: MatchWithDetails[],
  destStageId: number,
  matchLookup: Record<number, MatchLookupEntry>,
  stageOrder: StageWithStageItems[]
) {
  const oDest = stageOrderIndex(stageOrder, destStageId);
  for (let i = 0; i < G.length; i += 1) {
    const sid = matchLookup[G[i].id].stage.id;
    if (stageOrderIndex(stageOrder, sid) > oDest) {
      return i;
    }
  }
  return G.length;
}

/**
 * Rebuilds the on-court ordered list: replace the ordered subsequence of `destStageId` matches
 * in `G` with `Dnew` (in schedule order), or if none exist, splice `Dnew` in using
 * `findInsertForEmptyDestStage`.
 */
function mergeDestStageBlock(
  G: MatchWithDetails[],
  destStageId: number,
  Dnew: MatchWithDetails[],
  matchLookup: Record<number, MatchLookupEntry>,
  stageOrder: StageWithStageItems[]
) {
  if (Dnew.length < 1) {
    return G;
  }
  if (G.length < 1) {
    return Dnew.slice();
  }
  let destSeen = false;
  const out: MatchWithDetails[] = [];
  for (const m of G) {
    if (matchLookup[m.id].stage.id !== destStageId) {
      out.push(m);
    } else if (!destSeen) {
      out.push(...Dnew);
      destSeen = true;
    }
  }
  if (!destSeen) {
    const at = findInsertForEmptyDestStage(G, destStageId, matchLookup, stageOrder);
    const copy = G.slice();
    copy.splice(at, 0, ...Dnew);
    return copy;
  }
  return out;
}

/**
 * Converts a @hello-pangea index inside the destination *stage* droppable to the `new_position`
 * index expected by the reschedule API (global 0-based position on that court).
 */
function newPositionAfterMultiStageDrop(
  scheduledOnDestCourt: MatchWithDetails[],
  destStageId: number,
  localIndex: number,
  dragged: MatchWithDetails,
  fromSameCourt: boolean,
  matchLookup: Record<number, MatchLookupEntry>,
  stageOrder: StageWithStageItems[]
) {
  const G = fromSameCourt
    ? scheduledOnDestCourt.filter((m) => m.id !== dragged.id)
    : scheduledOnDestCourt;
  const D: MatchWithDetails[] = G.filter((m) => matchLookup[m.id].stage.id === destStageId);
  const n = D.length;
  const idx = Math.max(0, Math.min(localIndex, n));
  const Dnew: MatchWithDetails[] = [...D.slice(0, idx), dragged, ...D.slice(idx)];
  return mergeDestStageBlock(G, destStageId, Dnew, matchLookup, stageOrder).findIndex(
    (m) => m.id === dragged.id
  );
}

function getMatchStateColor(state: string) {
  if (state === 'IN_PROGRESS') return 'blue';
  if (state === 'COMPLETED') return 'green';
  return 'gray';
}

function ScheduleRow({
  index,
  match,
  openMatchModal,
  stageItemsLookup,
  matchesLookup,
}: {
  index: number;
  match: MatchWithDetails;
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
}) {
  const { t } = useTranslation();
  return (
    <Draggable key={match.id} index={index} draggableId={`${match.id}`}>
      {(provided) => (
        <div ref={provided.innerRef} {...provided.draggableProps}>
          <Card
            shadow="sm"
            padding="lg"
            radius="md"
            withBorder
            mt="md"
            onClick={() => {
              openMatchModal(match);
            }}
            {...provided.dragHandleProps}
          >
            <Grid>
              <Grid.Col span="auto">
                <Group gap="xs">
                  {match.stage_item_input1_conflict && <AiFillWarning color="red" />}
                  <Text fw={500}>
                    {formatMatchInput1(t, stageItemsLookup, matchesLookup, match)}
                  </Text>
                </Group>
                <Group gap="xs">
                  {match.stage_item_input2_conflict && <AiFillWarning color="red" />}
                  <Text fw={500}>
                    {formatMatchInput2(t, stageItemsLookup, matchesLookup, match)}
                  </Text>
                </Group>
              </Grid.Col>
              <Grid.Col span="content">
                <Stack gap="xs" align="end">
                  <Badge variant="default" size="lg">
                    {match.start_time != null ? <Time datetime={match.start_time} /> : null}
                  </Badge>
                  <Badge color={getMatchStateColor(match.state)} variant="light">
                    {t(`match_state_${String(match.state).toLowerCase()}`)}
                  </Badge>
                  <Badge
                    color={stringToColour(`${matchesLookup[match.id].stageItem.id}`)}
                    variant="outline"
                  >
                    {matchesLookup[match.id].stageItem.name}
                  </Badge>
                </Stack>
              </Grid.Col>
            </Grid>
          </Card>
        </div>
      )}
    </Draggable>
  );
}

/** Unscheduled matches that belong to `stageId` (keeps the order from `allUnscheduled`). */
function unscheduledForStage(
  allUnscheduled: MatchWithDetails[],
  matchLookup: Record<number, MatchLookupEntry>,
  stageId: number
) {
  return allUnscheduled.filter((m) => matchLookup[m.id].stage.id === stageId);
}

function UnscheduledColumn({
  matches,
  openMatchModal,
  stageItemsLookup,
  matchesLookup,
}: {
  matches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
}) {
  const { t } = useTranslation();
  const theme = useMantineTheme();
  const { colorScheme } = useMantineColorScheme();

  const subtleLaneBg =
    colorScheme === 'dark' ? alpha(theme.white, 0.045) : alpha(theme.black, 0.022);
  const subtleLaneBorder =
    colorScheme === 'dark' ? alpha(theme.colors.dark[2], 0.4) : alpha(theme.colors.gray[6], 0.35);

  const rows = matches.map((m, index) => (
    <ScheduleRow
      key={m.id}
      index={index}
      stageItemsLookup={stageItemsLookup}
      matchesLookup={matchesLookup}
      match={m}
      openMatchModal={openMatchModal}
    />
  ));

  const noItemsAlert =
    matches.length < 1 ? (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('all_matches_scheduled_title')}
        color="green"
        radius="md"
        mt="1rem"
      >
        {t('unscheduled_column_empty_description')}
      </Alert>
    ) : null;

  return (
    <Droppable droppableId={UNSCHEDULED_DROPPABLE_ID} direction="vertical">
      {(provided) => (
        <div {...provided.droppableProps} ref={provided.innerRef}>
          <Paper
            shadow="none"
            p="md"
            radius="md"
            withBorder
            style={{
              width: COL_WIDTH,
              borderStyle: 'dashed',
              borderWidth: 2,
              borderColor: subtleLaneBorder,
              backgroundColor: subtleLaneBg,
              minHeight: 200,
            }}
          >
            <Title order={4} mb="sm" ta="center">
              {t('unscheduled_title')}
            </Title>
            {rows}
            {noItemsAlert}
            {provided.placeholder}
          </Paper>
        </div>
      )}
    </Droppable>
  );
}

/**
 * Multi-stage planning grid: full-width `Divider` per stage, per-stage column headers, then
 * one droppable per (unscheduled or court, stage) pair so drag targets stay unambiguous.
 */
function StackedScheduleView({
  t,
  stages,
  tournament,
  swrCourtsResponse,
  stageItemsLookup,
  matchesLookup,
  schedule,
  unscheduledMatches,
  openMatchModal,
}: {
  t: Translator;
  stages: StageWithStageItems[];
  tournament: TournamentMinimal;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  schedule: { court: Court; matches: MatchWithDetails[] }[];
  unscheduledMatches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
}) {
  const { colorScheme } = useMantineColorScheme();
  const theme = useMantineTheme();
  if (schedule.length < 1) {
    return (
      <Stack align="center">
        <NoContent title={t('no_courts_title')} description={t('no_courts_description')} />
        <CourtModal
          swrCourtsResponse={swrCourtsResponse}
          tournamentId={tournament.id}
          buttonSize="lg"
        />
      </Stack>
    );
  }

  const subtleLaneBg =
    colorScheme === 'dark' ? alpha(theme.white, 0.045) : alpha(theme.black, 0.022);
  const subtleLaneBorder =
    colorScheme === 'dark' ? alpha(theme.colors.dark[2], 0.4) : alpha(theme.colors.gray[6], 0.35);
  const firstStageId = stages[0]?.id;

  const hasAnyOnCourt = (courtId: number) =>
    (schedule.find((s) => s.court.id === courtId)?.matches.length ?? 0) > 0;

  return (
    <Stack gap="md" w="100%" align="stretch" maw="100%">
      {stages.map((stage, stageIndex) => {
        const unschedForThisStage = unscheduledForStage(
          unscheduledMatches,
          matchesLookup,
          stage.id
        );
        return (
          <Box key={stage.id} w="100%">
            <Divider
              size="xs"
              my="md"
              label={stage.name}
              labelPosition="center"
              color="gray"
              c="dimmed"
              styles={{ label: { color: 'var(--mantine-color-dimmed)' } }}
            />
            <Group wrap="nowrap" align="center" mb="sm" gap="md">
              <Paper
                p="md"
                radius="md"
                style={{
                  width: COL_WIDTH,
                  flex: '0 0 auto',
                  borderStyle: 'dashed',
                  borderWidth: 0,
                }}
              >
                <Title order={4} ta="center" style={{ lineHeight: 1.2 }}>
                  {t('unscheduled_title')}
                </Title>
              </Paper>
              {schedule.map((item) => (
                <Group
                  key={`${stage.id}-hdr-${item.court.id}`}
                  wrap="nowrap"
                  align="center"
                  justify="space-between"
                  gap={0}
                  style={{ width: COL_WIDTH, flex: '0 0 auto' }}
                >
                  <Box
                    style={{
                      width: 36,
                      minWidth: 36,
                      flex: '0 0 36px',
                      flexShrink: 0,
                    }}
                  />
                  <Title
                    order={4}
                    ta="center"
                    style={{
                      margin: 0,
                      lineHeight: 1.2,
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    {item.court.name}
                  </Title>
                  <Box
                    style={{
                      width: 36,
                      minWidth: 36,
                      flex: '0 0 36px',
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <Menu withinPortal position="bottom-end" shadow="sm">
                      <Menu.Target>
                        <ActionIcon variant="transparent" color="gray" size="sm">
                          <IconDots size="1.25rem" />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item
                          leftSection={<IconTrash size="1.5rem" />}
                          onClick={async () => {
                            await deleteCourt(tournament.id, item.court.id);
                            await swrCourtsResponse.mutate();
                          }}
                          color="red"
                        >
                          {t('delete_court_button')}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Box>
                </Group>
              ))}
              <div style={{ width: COL_WIDTH, flex: '0 0 auto' }}>
                {stageIndex === 0 ? (
                  <CourtModal
                    swrCourtsResponse={swrCourtsResponse}
                    tournamentId={tournament.id}
                    buttonSize="xs"
                  />
                ) : null}
              </div>
            </Group>
            <Group wrap="nowrap" align="stretch" gap="md">
              <div style={{ width: COL_WIDTH, flex: '0 0 auto', display: 'flex' }}>
                <Droppable droppableId={unschedDroppableIdForStage(stage.id)} direction="vertical">
                  {(provided) => (
                    <div
                      {...provided.droppableProps}
                      ref={provided.innerRef}
                      style={{ width: '100%', display: 'flex' }}
                    >
                      <Paper
                        shadow="none"
                        p="md"
                        radius="md"
                        withBorder
                        style={{
                          width: COL_WIDTH,
                          borderStyle: 'dashed',
                          borderWidth: 2,
                          borderColor: subtleLaneBorder,
                          backgroundColor: subtleLaneBg,
                          minHeight: 100,
                          flex: 1,
                        }}
                      >
                        {unschedForThisStage.map((m, index) => (
                          <ScheduleRow
                            key={m.id}
                            index={index}
                            stageItemsLookup={stageItemsLookup}
                            matchesLookup={matchesLookup}
                            match={m}
                            openMatchModal={openMatchModal}
                          />
                        ))}
                        {unschedForThisStage.length < 1 ? (
                          <Alert
                            icon={<IconAlertCircle size={16} />}
                            title={t('all_matches_scheduled_title')}
                            color="green"
                            radius="md"
                            mt="0.5rem"
                          >
                            {t('unscheduled_column_empty_description')}
                          </Alert>
                        ) : null}
                        {provided.placeholder}
                      </Paper>
                    </div>
                  )}
                </Droppable>
              </div>

              {schedule.map((item) => {
                const slice = item.matches.filter((m) => matchesLookup[m.id].stage.id === stage.id);
                return (
                  <div
                    key={`${item.court.id}-${stage.id}`}
                    style={{ width: COL_WIDTH, flex: '0 0 auto', minHeight: 100, display: 'flex' }}
                  >
                    <Droppable
                      droppableId={courtStageDroppableId(item.court.id, stage.id)}
                      direction="vertical"
                    >
                      {(provided) => (
                        <div
                          {...provided.droppableProps}
                          ref={provided.innerRef}
                          style={{ width: '100%', display: 'flex' }}
                        >
                          <div style={{ width: '100%', flex: 1 }}>
                            {slice.map((m, index) => (
                              <ScheduleRow
                                key={m.id}
                                index={index}
                                stageItemsLookup={stageItemsLookup}
                                matchesLookup={matchesLookup}
                                match={m}
                                openMatchModal={openMatchModal}
                              />
                            ))}
                            {stage.id === firstStageId &&
                              slice.length < 1 &&
                              !hasAnyOnCourt(item.court.id) && (
                                <Alert
                                  icon={<IconAlertCircle size={16} />}
                                  title={t('no_matches_title')}
                                  color="gray"
                                  radius="md"
                                  mt="0.5rem"
                                >
                                  {t('drop_match_alert_title')}
                                </Alert>
                              )}
                            {provided.placeholder}
                          </div>
                        </div>
                      )}
                    </Droppable>
                  </div>
                );
              })}
              <div style={{ width: COL_WIDTH, flex: '0 0 auto' }} />
            </Group>
          </Box>
        );
      })}
    </Stack>
  );
}

function ScheduleColumn({
  tournamentId,
  court,
  matches,
  openMatchModal,
  stageItemsLookup,
  swrCourtsResponse,
  matchesLookup,
}: {
  tournamentId: number;
  court: Court;
  matches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  matchesLookup: Record<number, MatchLookupEntry>;
}) {
  const { t } = useTranslation();
  const rows = matches.map((m: MatchWithDetails, index: number) => (
    <ScheduleRow
      key={m.id}
      index={index}
      stageItemsLookup={stageItemsLookup}
      matchesLookup={matchesLookup}
      match={m}
      openMatchModal={openMatchModal}
    />
  ));

  const noItemsAlert =
    matches.length < 1 ? (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title={t('no_matches_title')}
        color="gray"
        radius="md"
        mt="1rem"
      >
        {t('drop_match_alert_title')}
      </Alert>
    ) : null;

  return (
    <Droppable droppableId={`${court.id}`} direction="vertical">
      {(provided) => (
        <div {...provided.droppableProps} ref={provided.innerRef}>
          <div style={{ width: COL_WIDTH }}>
            <Group justify="space-between">
              <Group>
                <h4 style={{ marginTop: '0', margin: 'auto' }}>{court.name}</h4>
              </Group>
              <Menu withinPortal position="bottom-end" shadow="sm">
                <Menu.Target>
                  <ActionIcon variant="transparent" color="gray">
                    <IconDots size="1.25rem" />
                  </ActionIcon>
                </Menu.Target>

                <Menu.Dropdown>
                  <Menu.Item
                    leftSection={<IconTrash size="1.5rem" />}
                    onClick={async () => {
                      await deleteCourt(tournamentId, court.id);
                      await swrCourtsResponse.mutate();
                    }}
                    color="red"
                  >
                    {t('delete_court_button')}
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
            {rows}
            {noItemsAlert}
            {provided.placeholder}
          </div>
        </div>
      )}
    </Droppable>
  );
}

/**
 * Renders the planning board: `StackedScheduleView` when the tournament has 2+ stages, otherwise
 * a single row of unscheduled + court droppables (legacy ids) for one stage.
 */
function Schedule({
  t,
  stages,
  tournament,
  swrCourtsResponse,
  stageItemsLookup,
  matchesLookup,
  schedule,
  unscheduledMatches,
  openMatchModal,
}: {
  t: Translator;
  stages: StageWithStageItems[] | null;
  tournament: TournamentMinimal;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  schedule: { court: Court; matches: MatchWithDetails[] }[];
  unscheduledMatches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
}) {
  if (stages != null && stages.length > 1) {
    return (
      <StackedScheduleView
        t={t}
        stages={stages}
        tournament={tournament}
        swrCourtsResponse={swrCourtsResponse}
        stageItemsLookup={stageItemsLookup}
        matchesLookup={matchesLookup}
        schedule={schedule}
        unscheduledMatches={unscheduledMatches}
        openMatchModal={openMatchModal}
      />
    );
  }

  if (schedule.length < 1) {
    return (
      <Stack align="center">
        <NoContent title={t('no_courts_title')} description={t('no_courts_description')} />
        <CourtModal
          swrCourtsResponse={swrCourtsResponse}
          tournamentId={tournament.id}
          buttonSize="lg"
        />
      </Stack>
    );
  }

  return (
    <Group wrap="nowrap" align="top">
      <UnscheduledColumn
        key="unscheduled"
        matches={unscheduledMatches}
        openMatchModal={openMatchModal}
        stageItemsLookup={stageItemsLookup}
        matchesLookup={matchesLookup}
      />
      {schedule.map((item) => (
        <ScheduleColumn
          key={item.court.id}
          tournamentId={tournament.id}
          swrCourtsResponse={swrCourtsResponse}
          stageItemsLookup={stageItemsLookup}
          matchesLookup={matchesLookup}
          court={item.court}
          matches={item.matches}
          openMatchModal={openMatchModal}
        />
      ))}
      <div key="add-court" style={{ width: COL_WIDTH }}>
        <CourtModal
          swrCourtsResponse={swrCourtsResponse}
          tournamentId={tournament.id}
          buttonSize="xs"
        />
      </div>
    </Group>
  );
}

export default function SchedulePage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);

  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  const swrStagesResponse = getStages(tournamentData.id);
  const swrCourtsResponse = getCourts(tournamentData.id);

  const stageItemsLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLookup(swrStagesResponse)
    : [];
  const matchesLookup: Record<number, MatchLookupEntry> = responseIsValid(swrStagesResponse)
    ? getMatchLookup(swrStagesResponse)
    : ({} as Record<number, MatchLookupEntry>);
  const matchesByCourtId = responseIsValid(swrStagesResponse)
    ? getMatchLookupByCourt(swrStagesResponse)
    : [];

  const data =
    responseIsValid(swrCourtsResponse) && responseIsValid(swrStagesResponse)
      ? getScheduleData(swrCourtsResponse, matchesByCourtId)
      : [];

  const unscheduledMatches = responseIsValid(swrStagesResponse)
    ? getUnscheduledMatches(swrStagesResponse)
    : [];

  if (!responseIsValid(swrStagesResponse)) return null;
  if (!responseIsValid(swrCourtsResponse)) return null;

  const rawStages: StageWithStageItems[] = swrStagesResponse.data?.data ?? [];
  const multi = rawStages.length > 1;

  function openMatchModal(matchToOpen: MatchWithDetails) {
    setMatch(matchToOpen);
    modalSetOpened(true);
  }

  const handleDragEnd: Parameters<typeof DragDropContext>[0]['onDragEnd'] = async ({
    destination,
    source,
    draggableId: matchIdStr,
  }) => {
    if (destination == null || source == null) return;

    const fromUnsched = isUnschedDroppableId(source.droppableId);
    const toUnsched = isUnschedDroppableId(destination.droppableId);
    if (fromUnsched && toUnsched) {
      if (source.droppableId === destination.droppableId) {
        return;
      }
      await swrStagesResponse.mutate();
      return;
    }

    const matchId = +matchIdStr;
    const m = matchesLookup[matchId]?.match;
    if (m == null) return;

    if (toUnsched) {
      await unscheduleMatch(tournamentData.id, matchId);
    } else if (multi) {
      const toParsed = tryParseCourtDroppableId(destination.droppableId);
      if (toParsed == null) return;
      const destCourt = data.find((d) => d.court.id === toParsed.courtId);
      if (destCourt == null) return;
      const fromSameCourt = m.court_id === toParsed.courtId;
      const newPos = newPositionAfterMultiStageDrop(
        destCourt.matches,
        toParsed.stageId,
        destination.index,
        m,
        fromSameCourt,
        matchesLookup,
        rawStages
      );
      await rescheduleMatch(tournamentData.id, matchId, {
        old_court_id: m.court_id != null && m.start_time != null ? m.court_id : null,
        old_position:
          m.court_id != null && m.start_time != null
            ? assert_not_none(m.position_in_schedule)
            : null,
        new_court_id: toParsed.courtId,
        new_position: newPos,
      });
    } else {
      await rescheduleMatch(tournamentData.id, matchId, {
        old_court_id: fromUnsched ? null : +source.droppableId,
        old_position: fromUnsched ? null : source.index,
        new_court_id: +destination.droppableId,
        new_position: destination.index,
      });
    }
    await swrStagesResponse.mutate();
  };

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      {match != null ? (
        <MatchModal
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={null}
          tournamentData={tournamentData}
          match={match}
          opened={modalOpened}
          setOpened={modalSetOpened}
          round={null}
        />
      ) : null}
      <Grid grow>
        <Grid.Col span={6}>
          <Title>{t('planning_title')}</Title>
        </Grid.Col>
        <Grid.Col span={6}>
          {data.length < 1 ? null : (
            <Group justify="right">
              <Button
                color="indigo"
                size="md"
                variant="filled"
                style={{ marginBottom: 10 }}
                leftSection={<IconCalendarPlus size={24} />}
                onClick={async () => {
                  await scheduleMatches(tournamentData.id);
                  await swrStagesResponse.mutate();
                }}
              >
                {t('schedule_description')}
              </Button>
            </Group>
          )}
        </Grid.Col>
      </Grid>
      <Group grow mt="1rem" wrap="wrap">
        <DragDropContext onDragEnd={handleDragEnd}>
          <Schedule
            t={t}
            stages={multi ? rawStages : null}
            tournament={tournamentData}
            swrCourtsResponse={swrCourtsResponse}
            schedule={data}
            unscheduledMatches={unscheduledMatches}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            openMatchModal={openMatchModal}
          />
        </DragDropContext>
      </Group>
    </TournamentLayout>
  );
}
