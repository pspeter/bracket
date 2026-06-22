import { Button, Container, Grid, Group, SegmentedControl, Stack, Title } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';
import { parseAsString, useQueryState } from 'nuqs';
import { useTranslation } from 'react-i18next';
import { LuNavigation } from 'react-icons/lu';
import { SWRResponse } from 'swr';

import { SwissRoundsGrid } from '@components/brackets/brackets';
import { NoContent } from '@components/no_content/empty_table_info';
import classes from '@components/utility.module.css';
import { BracketDisplaySettings } from '@components/utils/brackets';
import PreloadLink from '@components/utils/link';
import { Translator } from '@components/utils/types';
import {
  getStageItemIdFromRouter,
  getTournamentIdFromRouter,
  responseIsValid,
} from '@components/utils/util';
import { TournamentWithLevels } from '@openapi';
import NotFoundTitle from '@pages/404';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { checkForAuthError, getCourts, getStages, getTournamentById } from '@services/adapter';
import { getStageItemLookup } from '@services/lookups';

function NoCourtsButton({
  t,
  tournamentData,
}: {
  t: Translator;
  tournamentData: TournamentWithLevels;
}) {
  return (
    <Stack align="center">
      <NoContent title={t('no_courts_title')} description={t('no_courts_description_swiss')} />
      <Button
        color="green"
        size="lg"
        leftSection={<LuNavigation size={24} />}
        variant="outline"
        component={PreloadLink}
        className={classes.mobileLink}
        href={`/tournaments/${tournamentData.id}/schedule`}
      >
        {t('go_to_courts_page')}
      </Button>
    </Stack>
  );
}

export default function SwissTournamentPage() {
  const { id, tournamentData } = getTournamentIdFromRouter();
  const stageItemId = getStageItemIdFromRouter();
  const { t } = useTranslation();

  const swrTournamentResponse = getTournamentById(tournamentData.id);
  checkForAuthError(swrTournamentResponse);
  const swrStagesResponse: SWRResponse = getStages(id);
  const swrCourtsResponse = getCourts(tournamentData.id);

  const [matchVisibility, setMatchVisibility] = useQueryState(
    'match-visibility',
    parseAsString.withDefault('all')
  );
  const [teamNamesDisplay, setTeamNamesDisplay] = useQueryState(
    'which-names',
    parseAsString.withDefault('team-names')
  );

  const displaySettings: BracketDisplaySettings = {
    matchVisibility,
    setMatchVisibility,
    teamNamesDisplay,
    setTeamNamesDisplay,
  };

  const tournamentDataFull = swrTournamentResponse.data?.data;

  let stageItem = null;

  if (responseIsValid(swrStagesResponse) && stageItemId != null) {
    stageItem = getStageItemLookup(swrStagesResponse)[stageItemId];
  }

  if (!swrTournamentResponse.isLoading && tournamentDataFull == null) {
    return <NotFoundTitle />;
  } else if (tournamentDataFull == null) {
    return null;
  }

  if (
    !swrCourtsResponse.isLoading &&
    swrCourtsResponse.data &&
    swrCourtsResponse.data.data.length < 1
  ) {
    return (
      <TournamentLayout tournament_id={tournamentData.id}>
        <Container mt="1rem">
          <Stack align="center">
            <NoCourtsButton t={t} tournamentData={tournamentDataFull} />
          </Stack>
        </Container>
      </TournamentLayout>
    );
  }

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Grid grow>
        <Grid.Col span={6}>
          <Title>{stageItem != null ? stageItem.name : ''}</Title>
        </Grid.Col>
        <Grid.Col span={6}>
          <Group justify="right">
            <SegmentedControl
              className={classes.fullWithMobile}
              value={matchVisibility}
              onChange={setMatchVisibility}
              data={[
                { label: t('match_filter_option_all'), value: 'all' },
                { label: t('match_filter_option_past'), value: 'future-only' },
                { label: t('match_filter_option_current'), value: 'present-only' },
              ]}
            />
            {tournamentDataFull?.dashboard_endpoint && (
              <Button
                className={classes.fullWithMobile}
                color="blue"
                size="sm"
                variant="outline"
                leftSection={<IconExternalLink size={24} />}
                onClick={() => {
                  window.open(
                    `/tournaments/${tournamentDataFull.dashboard_endpoint}/dashboard`,
                    '_ blank'
                  );
                }}
              >
                {t('view_dashboard_button')}
              </Button>
            )}
          </Group>
        </Grid.Col>
      </Grid>
      <div style={{ marginTop: '1rem', marginLeft: '1rem', marginRight: '1rem' }}>
        {stageItem != null && (
          <SwissRoundsGrid
            tournamentData={tournamentDataFull}
            swrStagesResponse={swrStagesResponse}
            stageItem={stageItem}
            displaySettings={displaySettings}
          />
        )}
      </div>
    </TournamentLayout>
  );
}
