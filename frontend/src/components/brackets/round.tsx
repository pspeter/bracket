import { Badge, Center, Grid, Group, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import RoundModal from '@components/modals/round_modal';
import { BracketDisplaySettings } from '@components/utils/brackets';
import { isMatchHappening, isMatchInTheFutureOrPresent } from '@components/utils/match';
import { TournamentMinimal } from '@components/utils/tournament';
import {
  MatchWithDetails,
  RoundLifecycleState,
  RoundWithMatches,
  StagesWithStageItemsResponse,
} from '@openapi';
import Match from './match';

function lifecycleBadge(t: any, state: RoundLifecycleState) {
  const cfg: Record<RoundLifecycleState, { color: string; label: string }> = {
    PLACEHOLDER: { color: 'gray', label: t('round_lifecycle_placeholder') },
    RESOLVED: { color: 'blue', label: t('round_lifecycle_resolved') },
    ACTIVE: { color: 'green', label: t('round_lifecycle_active') },
    LOCKED: { color: 'dark', label: t('round_lifecycle_locked') },
  };
  const { color, label } = cfg[state] ?? { color: 'gray', label: state };
  return (
    <Badge color={color} variant="light" size="sm">
      {label}
    </Badge>
  );
}

export default function RoundComponent({
  tournamentData,
  round,
  swrStagesResponse,
  readOnly,
  displaySettings,
  showLifecycleState = false,
}: {
  tournamentData: TournamentMinimal;
  round: RoundWithMatches;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  readOnly: boolean;
  displaySettings: BracketDisplaySettings;
  showLifecycleState?: boolean;
}) {
  const { t } = useTranslation();
  const matches = round.matches
    .sort((m1, m2) =>
      (m1.court ? m1.court.name : 'y') > (m2.court ? m2.court.name : 'z') ? 1 : -1
    )
    .filter(
      (match: MatchWithDetails) =>
        displaySettings.matchVisibility === 'all' ||
        (displaySettings.matchVisibility === 'future-only' && isMatchInTheFutureOrPresent(match)) ||
        (displaySettings.matchVisibility === 'present-only' && isMatchHappening(match))
    )
    .map((match) => (
      <Match
        key={match.id}
        tournamentData={tournamentData}
        swrStagesResponse={swrStagesResponse}
        match={match}
        readOnly={readOnly}
        round={round}
      />
    ));
  const isPlaceholder = round.lifecycle_state === 'PLACEHOLDER';
  const roundBorderStyle = {
    borderStyle: isPlaceholder ? 'dashed' : 'solid',
    borderColor: 'gray',
  };

  const modal = readOnly ? (
    <Title order={3}>{round.name}</Title>
  ) : (
    <RoundModal
      tournamentData={tournamentData}
      round={round}
      swrStagesResponse={swrStagesResponse}
    />
  );

  if (matches.length === 0 && displaySettings.matchVisibility !== 'all') {
    return null;
  }

  const item = (
    <div
      style={{
        height: '100%',
        minHeight: 320,
        padding: '15px',
        borderRadius: '20px',
        ...roundBorderStyle,
      }}
    >
      <Center>
        <Group gap="xs" justify="center">
          {modal}
          {showLifecycleState && lifecycleBadge(t, round.lifecycle_state)}
        </Group>
      </Center>
      {matches}
    </div>
  );

  if (readOnly) {
    return (
      <Grid.Col
        style={{ minHeight: 320, maxWidth: 500, marginRight: '1rem', marginBottom: '1rem' }}
      >
        {item}
      </Grid.Col>
    );
  }

  return (
    <div style={{ minHeight: 320, width: 400, marginRight: '1rem', marginBottom: '1rem' }}>
      {item}
    </div>
  );
}
