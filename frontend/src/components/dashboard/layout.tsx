import {
  Box,
  Button,
  Center,
  Container,
  Group,
  Image,
  Select,
  Skeleton,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { parseAsInteger, useQueryState } from 'nuqs';
import { useTranslation } from 'react-i18next';
import QRCode from 'react-qr-code';
import { useLocation } from 'react-router';

import { levelSelectData } from '@components/levels/levels';
import PreloadLink from '@components/utils/link';
import { getBaseURL } from '@components/utils/util';
import { TournamentWithLevels } from '@openapi';
import { getBaseApiUrl, getTeamsForDashboard } from '@services/adapter';
import classes from './layout.module.css';
import { TeamFilterCombobox } from './team_filter';

export function TournamentQRCode({
  tournamentDataFull,
}: {
  tournamentDataFull: TournamentWithLevels;
}) {
  if (tournamentDataFull == null) {
    return null;
  }
  return (
    <div
      style={{
        width: '100%',
        background: 'white',
        marginTop: '2rem',
        maxWidth: '400px',
        height: 'auto',
        borderRadius: '16px',
        alignSelf: 'end',
      }}
    >
      <Center>
        <QRCode
          style={{ margin: '24px' }}
          // @ts-ignore
          size="auto"
          value={`${getBaseURL()}/tournaments/${tournamentDataFull.dashboard_endpoint}/dashboard`}
        />
      </Center>
    </div>
  );
}

export function TournamentLogo({
  tournamentDataFull,
}: {
  tournamentDataFull: TournamentWithLevels;
}) {
  if (tournamentDataFull == null) {
    return <Skeleton height={150} radius="xl" mb="xl" />;
  }
  return tournamentDataFull.logo_path ? (
    <>
      <Image
        radius="lg"
        mt="1rem"
        alt="Logo of the tournament"
        src={`${getBaseApiUrl()}/static/tournament-logos/${tournamentDataFull.logo_path}`}
        style={{ maxWidth: '400px' }}
      />
    </>
  ) : null;
}

export function getTournamentHeadTitle(tournamentDataFull: TournamentWithLevels) {
  return tournamentDataFull !== null ? `Bracket | ${tournamentDataFull.name}` : 'Bracket';
}

export function TournamentTitle({
  tournamentDataFull,
}: {
  tournamentDataFull: TournamentWithLevels;
}) {
  return tournamentDataFull != null ? (
    <Title>{tournamentDataFull.name}</Title>
  ) : (
    <Skeleton height={50} radius="lg" mb="xl" />
  );
}

export function DoubleHeader({ tournamentData }: { tournamentData: TournamentWithLevels }) {
  const { t } = useTranslation();
  const navigate = useLocation();
  const endpoint = tournamentData.dashboard_endpoint || '';
  const pathName = navigate.pathname.replace('[id]', endpoint).replace(/\/+$/, '');
  const [levelId, setLevelId] = useQueryState('level', parseAsInteger);
  const [teamId, setTeamId] = useQueryState('team', parseAsInteger);

  // Only teams from the selected level are offered (when a level is selected).
  const { teams } = getTeamsForDashboard(tournamentData.id, levelId);
  const teamOptions = teams.map((team) => ({ value: `${team.id}`, label: team.name }));

  // Keep both filters in the URL so they survive navigating between tabs.
  const filterParams = new URLSearchParams();
  if (levelId != null) filterParams.set('level', `${levelId}`);
  if (teamId != null) filterParams.set('team', `${teamId}`);
  const filterQuery = filterParams.toString();
  const filterSuffix = filterQuery ? `?${filterQuery}` : '';

  const onLevelChange = (val: string | null) => {
    const nextLevelId = val === 'all' || val === null ? null : parseInt(val, 10);
    setLevelId(nextLevelId);
    // Selecting a specific level invalidates a team that may belong to another level.
    if (nextLevelId != null && teamId != null) {
      setTeamId(null);
    }
  };

  const onTeamChange = (nextTeamId: number | null) => {
    setTeamId(nextTeamId);
    // When picking a team without a level filter, also scope to that team's level.
    if (nextTeamId != null && levelId == null) {
      const team = teams.find((candidate) => candidate.id === nextTeamId);
      if (team?.level_id != null) {
        setLevelId(team.level_id);
      }
    }
  };

  const clearFilters = () => {
    setLevelId(null);
    setTeamId(null);
  };

  const mainLinks = [
    { link: `/tournaments/${endpoint}/dashboard${filterSuffix}`, label: t('dashboard_tab_live') },
    {
      link: `/tournaments/${endpoint}/dashboard/matches${filterSuffix}`,
      label: t('dashboard_tab_matches'),
    },
    {
      link: `/tournaments/${endpoint}/dashboard/standings${filterSuffix}`,
      label: t('dashboard_tab_standings'),
    },
    ...(tournamentData.rules?.trim()
      ? [
          {
            link: `/tournaments/${endpoint}/dashboard/rules`,
            label: t('dashboard_tab_rules'),
          },
        ]
      : []),
  ];

  const mainItems = mainLinks.map((item) => (
    <PreloadLink
      href={item.link}
      key={item.label}
      className={classes.mainLink}
      data-active={item.link.split('?')[0] === pathName || undefined}
    >
      {item.label}
    </PreloadLink>
  ));

  return (
    <header className={classes.header}>
      <Container className={classes.inner}>
        <UnstyledButton component={PreloadLink} href={`/tournaments/${endpoint}/dashboard`}>
          <Group gap="sm" wrap="nowrap">
            {tournamentData.logo_path && (
              <Image
                radius="sm"
                h={36}
                w="auto"
                alt="Tournament logo"
                src={`${getBaseApiUrl()}/static/tournament-logos/${tournamentData.logo_path}`}
              />
            )}
            <Title size="lg" lineClamp={1}>
              {tournamentData.name}
            </Title>
          </Group>
        </UnstyledButton>
        <Box className={classes.links}>
          <Group gap={0} className={classes.mainLinks}>
            {mainItems}
          </Group>
          <Group gap="xs" align="center" wrap="wrap" mt="xs">
            {tournamentData.levels.length > 0 && (
              <Select
                size="xs"
                w={130}
                data={levelSelectData(tournamentData.levels, t('all_levels_label'))}
                value={levelId != null ? `${levelId}` : 'all'}
                onChange={onLevelChange}
                placeholder={t('filter_level_placeholder')}
              />
            )}
            <TeamFilterCombobox
              value={teamId}
              onChange={onTeamChange}
              teamOptions={teamOptions}
              width={150}
            />
            {(levelId != null || teamId != null) && (
              <Button size="xs" variant="subtle" onClick={clearFilters}>
                {t('clear_filter_button')}
              </Button>
            )}
          </Group>
        </Box>
      </Container>
    </header>
  );
}
