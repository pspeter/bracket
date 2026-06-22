import { Center, Group, Select, Title } from '@mantine/core';
import { parseAsInteger, useQueryState } from 'nuqs';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { TeamFilterCombobox } from '@components/dashboard/team_filter';
import { levelSelectData } from '@components/levels/levels';
import { MatchesList } from '@components/matches/matches_list';
import MatchModal from '@components/modals/match_modal';
import { matchHasTeam } from '@components/utils/match';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { MatchWithDetails } from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getCourts, getStages, getTeamsForDashboard, getTournamentById } from '@services/adapter';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';

export default function ResultsPage() {
  const [modalOpened, modalSetOpened] = useState(false);
  const [match, setMatch] = useState<MatchWithDetails | null>(null);

  const { t } = useTranslation();
  const { tournamentData } = getTournamentIdFromRouter();
  const swrStagesResponse = getStages(tournamentData.id);
  const swrCourtsResponse = getCourts(tournamentData.id);
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const levels = swrTournamentResponse.data?.data.levels ?? [];
  const refereesEnabled = swrTournamentResponse.data?.data.referees_enabled ?? false;
  const [levelId, setLevelId] = useQueryState('level', parseAsInteger);
  const [teamId, setTeamId] = useQueryState('team', parseAsInteger);

  const { teams } = getTeamsForDashboard(tournamentData.id, levelId);
  const teamOptions = teams.map((team) => ({ value: `${team.id}`, label: team.name }));

  const stageItemsLookup = responseIsValid(swrStagesResponse)
    ? getStageItemLookup(swrStagesResponse)
    : [];
  const matchesLookup = responseIsValid(swrStagesResponse) ? getMatchLookup(swrStagesResponse) : [];

  const filteredMatchesLookup =
    levelId != null || teamId != null
      ? Object.fromEntries(
          Object.entries(matchesLookup).filter(
            ([, entry]: any) =>
              (levelId == null || entry.stage.level_id === levelId) &&
              (teamId == null || matchHasTeam(entry.match, teamId, refereesEnabled))
          )
        )
      : matchesLookup;

  if (!responseIsValid(swrStagesResponse)) return null;
  if (!responseIsValid(swrCourtsResponse)) return null;

  function openMatchModal(matchToOpen: MatchWithDetails) {
    setMatch(matchToOpen);
    modalSetOpened(true);
  }

  function modalSetOpenedAndUpdateMatch(opened: boolean) {
    if (!opened) {
      setMatch(null);
    }
    modalSetOpened(opened);
  }

  const onLevelChange = (val: string | null) => {
    const nextLevelId = val === 'all' || val === null ? null : parseInt(val, 10);
    setLevelId(nextLevelId);
    if (nextLevelId != null && teamId != null) {
      setTeamId(null);
    }
  };

  const onTeamChange = (nextTeamId: number | null) => {
    setTeamId(nextTeamId);
    if (nextTeamId != null && levelId == null) {
      const team = teams.find((candidate) => candidate.id === nextTeamId);
      if (team?.level_id != null) {
        setLevelId(team.level_id);
      }
    }
  };

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <MatchModal
        swrStagesResponse={swrStagesResponse}
        tournamentData={tournamentData}
        match={match}
        opened={modalOpened}
        setOpened={modalSetOpenedAndUpdateMatch}
        round={null}
        levels={levels}
      />
      <Group justify="space-between" align="center">
        <Title>{t('results_title')}</Title>
        <Group gap="xs">
          {levels.length > 0 && (
            <Select
              size="sm"
              w={160}
              data={levelSelectData(levels, t('all_levels_label'))}
              value={levelId != null ? `${levelId}` : 'all'}
              onChange={onLevelChange}
            />
          )}
          <TeamFilterCombobox
            value={teamId}
            onChange={onTeamChange}
            teamOptions={teamOptions}
            width={160}
          />
        </Group>
      </Group>
      <Center mt="1rem">
        <Group style={{ maxWidth: '48rem', width: '100%' }}>
          <MatchesList
            matchesLookup={filteredMatchesLookup}
            stageItemsLookup={stageItemsLookup}
            levels={levels}
            refereesEnabled={refereesEnabled}
            onMatchClick={openMatchModal}
          />
        </Group>
      </Center>
    </TournamentLayout>
  );
}
