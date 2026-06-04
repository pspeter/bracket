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

import { LevelBadge } from '@components/levels/levels';
import CourtModal from '@components/modals/create_court_modal';
import MatchModal from '@components/modals/match_modal';
import { NoContent } from '@components/no_content/empty_table_info';
import { assert_not_none } from '@components/utils/assert';
import { Time } from '@components/utils/datetime';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { TournamentMinimal } from '@components/utils/tournament';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import {
  Court,
  CourtsResponse,
  LevelResponse,
  MatchWithDetails,
  StageWithStageItems,
} from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getCourts, getStages, getTournamentById } from '@services/adapter';
import { deleteCourt } from '@services/court';
import {
  MatchLookupEntry,
  getMatchLookup,
  getMatchLookupByCourt,
  getScheduleData,
  getStageItemLookup,
  getStageOrderViolations,
  getUnscheduledMatches,
  stringToColour,
} from '@services/lookups';
import { rescheduleMatch, scheduleMatches, unscheduleMatch } from '@services/match';

const COL_WIDTH = '25rem';

function unschedLevelDroppableId(levelId: number | null) {
  return `ul-${levelId ?? 'null'}`;
}

function courtDroppableId(courtId: number) {
  return `c-${courtId}`;
}

function isUnschedDroppableId(droppableId: string) {
  return droppableId.startsWith('ul-');
}

function tryParseCourtDroppableId(droppableId: string): number | null {
  const m = droppableId.match(/^c-(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
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
  levels,
  isViolation,
}: {
  index: number;
  match: MatchWithDetails;
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
  isViolation?: boolean;
}) {
  const { t } = useTranslation();
  const entry = matchesLookup[match.id];
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
                  {isViolation && <AiFillWarning color="orange" />}
                  <Badge variant="default" size="lg">
                    {match.start_time != null ? <Time datetime={match.start_time} /> : null}
                  </Badge>
                  <Badge color={getMatchStateColor(match.state)} variant="light">
                    {t(`match_state_${String(match.state).toLowerCase()}`)}
                  </Badge>
                  <LevelBadge levels={levels} levelId={entry.stage.level_id} />
                  <Badge color={stringToColour(`${entry.stageItem.id}`)} variant="outline">
                    {entry.stage.name} · {entry.stageItem.name}
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

/** One unscheduled column per level (or a single "Unscheduled" column for no-level tournaments). */
function LevelUnscheduledColumn({
  levelId,
  levelName,
  stages,
  allUnscheduled,
  openMatchModal,
  stageItemsLookup,
  matchesLookup,
  levels,
}: {
  levelId: number | null;
  levelName: string;
  stages: StageWithStageItems[];
  allUnscheduled: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  levels: LevelResponse[];
}) {
  const { t } = useTranslation();
  const { colorScheme } = useMantineColorScheme();
  const theme = useMantineTheme();

  const subtleLaneBg =
    colorScheme === 'dark' ? alpha(theme.white, 0.045) : alpha(theme.black, 0.022);
  const subtleLaneBorder =
    colorScheme === 'dark' ? alpha(theme.colors.dark[2], 0.4) : alpha(theme.colors.gray[6], 0.35);

  const levelMatches = allUnscheduled.filter(
    (m) => (matchesLookup[m.id]?.stage.level_id ?? null) === levelId
  );

  // Group by stage; auto-hide stages with no unscheduled matches
  const levelStages = stages.filter((s) => (s.level_id ?? null) === levelId);
  const stageGroups = levelStages
    .map((stage) => ({
      stage,
      matches: levelMatches.filter((m) => matchesLookup[m.id]?.stage.id === stage.id),
    }))
    .filter((g) => g.matches.length > 0);

  const flatMatches = stageGroups.flatMap((g) => g.matches);
  const matchIndex = new Map(flatMatches.map((m, i) => [m.id, i]));

  return (
    <Droppable droppableId={unschedLevelDroppableId(levelId)} direction="vertical">
      {(provided) => (
        <div {...provided.droppableProps} ref={provided.innerRef}>
          <Paper
            shadow="none"
            p="md"
            radius="md"
            withBorder
            style={{
              width: COL_WIDTH,
              flex: '0 0 auto',
              borderStyle: 'dashed',
              borderWidth: 2,
              borderColor: subtleLaneBorder,
              backgroundColor: subtleLaneBg,
              minHeight: 200,
            }}
          >
            <Title order={4} mb="sm" ta="center">
              {levelName}
            </Title>
            {stageGroups.map((group) => (
              <Box key={group.stage.id}>
                <Divider
                  my="xs"
                  label={group.stage.name}
                  labelPosition="left"
                  c="dimmed"
                  styles={{ label: { color: 'var(--mantine-color-dimmed)', fontSize: '0.75rem' } }}
                />
                {group.matches.map((m) => (
                  <ScheduleRow
                    key={m.id}
                    index={matchIndex.get(m.id)!}
                    stageItemsLookup={stageItemsLookup}
                    matchesLookup={matchesLookup}
                    match={m}
                    openMatchModal={openMatchModal}
                    levels={levels}
                  />
                ))}
              </Box>
            ))}
            {levelMatches.length < 1 && (
              <Alert
                icon={<IconAlertCircle size={16} />}
                title={t('all_matches_scheduled_title')}
                color="green"
                radius="md"
                mt="1rem"
              >
                {t('unscheduled_column_empty_description')}
              </Alert>
            )}
            {provided.placeholder}
          </Paper>
        </div>
      )}
    </Droppable>
  );
}

/** Flat court column — no stage dividers; shows stage-order violation warnings on cards. */
function FlatCourtColumn({
  tournamentId,
  court,
  matches,
  openMatchModal,
  stageItemsLookup,
  swrCourtsResponse,
  matchesLookup,
  violations,
  levels,
}: {
  tournamentId: number;
  court: Court;
  matches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  matchesLookup: Record<number, MatchLookupEntry>;
  violations: Set<number>;
  levels: LevelResponse[];
}) {
  const { t } = useTranslation();

  return (
    <Droppable droppableId={courtDroppableId(court.id)} direction="vertical">
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
            {matches.map((m: MatchWithDetails, index: number) => (
              <ScheduleRow
                key={m.id}
                index={index}
                stageItemsLookup={stageItemsLookup}
                matchesLookup={matchesLookup}
                match={m}
                openMatchModal={openMatchModal}
                levels={levels}
                isViolation={violations.has(m.id)}
              />
            ))}
            {matches.length < 1 && (
              <Alert
                icon={<IconAlertCircle size={16} />}
                title={t('no_matches_title')}
                color="gray"
                radius="md"
                mt="1rem"
              >
                {t('drop_match_alert_title')}
              </Alert>
            )}
            {provided.placeholder}
          </div>
        </div>
      )}
    </Droppable>
  );
}

/**
 * Renders the planning board: per-level unscheduled columns followed by flat court columns.
 * Single-level and no-level tournaments use one unscheduled column (unified code path).
 */
function Schedule({
  stages,
  tournament,
  swrCourtsResponse,
  stageItemsLookup,
  matchesLookup,
  schedule,
  unscheduledMatches,
  openMatchModal,
  levels,
}: {
  stages: StageWithStageItems[];
  tournament: TournamentMinimal;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  stageItemsLookup: ReturnType<typeof getStageItemLookup> | never[];
  matchesLookup: Record<number, MatchLookupEntry>;
  schedule: { court: Court; matches: MatchWithDetails[] }[];
  unscheduledMatches: MatchWithDetails[];
  openMatchModal: (m: MatchWithDetails) => void;
  levels: LevelResponse[];
}) {
  const { t } = useTranslation();

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

  const unschedColumns =
    levels.length > 0
      ? levels.map((level) => ({ levelId: level.id as number | null, levelName: level.name }))
      : [{ levelId: null as number | null, levelName: t('unscheduled_title') }];

  return (
    <Group wrap="nowrap" align="top">
      {unschedColumns.map(({ levelId, levelName }) => (
        <LevelUnscheduledColumn
          key={`ul-${levelId ?? 'null'}`}
          levelId={levelId}
          levelName={levelName}
          stages={stages}
          allUnscheduled={unscheduledMatches}
          openMatchModal={openMatchModal}
          stageItemsLookup={stageItemsLookup}
          matchesLookup={matchesLookup}
          levels={levels}
        />
      ))}
      {schedule.map((item) => {
        const violations = getStageOrderViolations(item.matches, matchesLookup, stages);
        return (
          <FlatCourtColumn
            key={item.court.id}
            tournamentId={tournament.id}
            swrCourtsResponse={swrCourtsResponse}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            court={item.court}
            matches={item.matches}
            openMatchModal={openMatchModal}
            violations={violations}
            levels={levels}
          />
        );
      })}
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
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const levels = swrTournamentResponse.data?.data.levels ?? [];

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

    // Drag between unscheduled columns is a no-op (cannot change a match's level via drag)
    if (fromUnsched && toUnsched) return;

    const matchId = +matchIdStr;
    const m = matchesLookup[matchId]?.match;
    if (m == null) return;

    if (toUnsched) {
      await unscheduleMatch(tournamentData.id, matchId);
    } else {
      const destCourtId = tryParseCourtDroppableId(destination.droppableId);
      if (destCourtId == null) return;
      await rescheduleMatch(tournamentData.id, matchId, {
        old_court_id: m.court_id != null && m.start_time != null ? m.court_id : null,
        old_position:
          m.court_id != null && m.start_time != null
            ? assert_not_none(m.position_in_schedule)
            : null,
        new_court_id: destCourtId,
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
      <Box mt="1rem" style={{ overflowX: 'auto' }}>
        <DragDropContext onDragEnd={handleDragEnd}>
          <Schedule
            stages={rawStages}
            tournament={tournamentData}
            swrCourtsResponse={swrCourtsResponse}
            schedule={data}
            unscheduledMatches={unscheduledMatches}
            stageItemsLookup={stageItemsLookup}
            matchesLookup={matchesLookup}
            openMatchModal={openMatchModal}
            levels={levels}
          />
        </DragDropContext>
      </Box>
    </TournamentLayout>
  );
}
