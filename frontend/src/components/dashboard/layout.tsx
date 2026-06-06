import {
  Box,
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
import { getBaseApiUrl } from '@services/adapter';
import classes from './layout.module.css';

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

  const levelParam = levelId != null ? `?level=${levelId}` : '';
  const mainLinks = [
    { link: `/tournaments/${endpoint}/dashboard${levelParam}`, label: t('dashboard_tab_live') },
    {
      link: `/tournaments/${endpoint}/dashboard/matches${levelParam}`,
      label: t('dashboard_tab_matches'),
    },
    {
      link: `/tournaments/${endpoint}/dashboard/standings${levelParam}`,
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
          <Title size="lg" lineClamp={1}>
            {tournamentData.name}
          </Title>
        </UnstyledButton>
        <Box className={classes.links}>
          <Group gap="md" align="center" wrap="nowrap">
            <Group gap={0} className={classes.mainLinks}>
              {mainItems}
            </Group>
            {tournamentData.levels.length > 0 && (
              <Select
                size="xs"
                w={140}
                data={levelSelectData(tournamentData.levels, t('all_levels_label'))}
                value={levelId != null ? `${levelId}` : 'all'}
                onChange={(val) =>
                  setLevelId(val === 'all' || val === null ? null : parseInt(val, 10))
                }
                placeholder={t('filter_level_placeholder')}
              />
            )}
          </Group>
        </Box>
      </Container>
    </header>
  );
}
