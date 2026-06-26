import { Center, Grid, UnstyledButton, useMantineTheme } from '@mantine/core';
import { useColorScheme } from '@mantine/hooks';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import MatchModal from '@components/modals/match_modal';
import { assert_not_none } from '@components/utils/assert';
import { Time } from '@components/utils/datetime';
import {
  formatMatchInput1,
  formatMatchInput2,
  getMatchScore1,
  getMatchScore2,
  isMatchHappening,
} from '@components/utils/match';
import { RefereeDisplay } from '@components/utils/referee';
import { TournamentMinimal } from '@components/utils/tournament';
import { MatchSet, MatchWithDetails, RoundWithMatches, StagesWithStageItemsResponse } from '@openapi';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { getSetScoreColors, getSetsWon } from '../../utils/match_sets';
import classes from './match.module.css';

export function MatchBadge({ match, theme }: { match: MatchWithDetails; theme: any }) {
  const visibility = match.court ? 'visible' : 'hidden';
  const badgeColor = useColorScheme() ? theme.colors.blue[7] : theme.colors.blue[7];
  return (
    <Center style={{ transform: 'translateY(0%)', visibility }}>
      <div
        style={{
          width: '75%',
          backgroundColor: isMatchHappening(match) ? theme.colors.grape[9] : badgeColor,
          borderRadius: '8px 8px 0px 0px',
          padding: '4px 12px 4px 12px',
        }}
      >
        <Center>
          <b>
            {match.court?.name} |{' '}
            {match.start_time != null ? <Time datetime={match.start_time} /> : null}
          </b>
        </Center>
      </div>
    </Center>
  );
}

export default function Match({
  swrStagesResponse,
  tournamentData,
  match,
  readOnly,
  round,
  refereesEnabled = false,
}: {
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  tournamentData: TournamentMinimal;
  match: MatchWithDetails;
  readOnly: boolean;

  round: RoundWithMatches;
  refereesEnabled?: boolean;
}) {
  const { t } = useTranslation();
  const theme = useMantineTheme();
  const winner_style = {
    backgroundColor: theme.colors.green[9],
  };

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);

  const score1 = getMatchScore1(match);
  const score2 = getMatchScore2(match);
  const team1_style = score1 > score2 ? winner_style : {};
  const team2_style = score1 < score2 ? winner_style : {};

  // Placeholder rounds have no resolved teams yet, so show "TBD" for their unresolved
  // slots instead of the generic "Empty slot" fallback (PRD US 21).
  const emptyLabelKey = round.lifecycle_state === 'PLACEHOLDER' ? 'tbd_label' : 'empty_slot';
  const team1_label = formatMatchInput1(t, stageItemsLookup, matchesLookup, match, emptyLabelKey);
  const team2_label = formatMatchInput2(t, stageItemsLookup, matchesLookup, match, emptyLabelKey);

  const [opened, setOpened] = useState(false);

  const isMultiSet = match.num_sets > 1 && match.match_sets.length > 0;

  const scoreCell = (set: MatchSet, side: 's1' | 's2') => {
    const { s1, s2 } = getSetScoreColors(set);
    const bg = side === 's1' ? s1 : s2;
    const value = side === 's1' ? set.stage_item_input1_score : set.stage_item_input2_score;
    const fz = match.num_sets > 3 ? '0.6rem' : '0.75rem';
    return (
      <div
        key={set.id}
        style={{
          backgroundColor: bg,
          borderRadius: '0.25rem',
          color: 'white',
          fontWeight: 800,
          fontSize: fz,
          minWidth: '1.5rem',
          textAlign: 'center',
          padding: '0 3px',
        }}
      >
        {value}
      </div>
    );
  };

  const multiSetScores = (side: 's1' | 's2') => (
    <div style={{ display: 'flex', gap: '2px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
      {match.match_sets.map((set) => scoreCell(set, side))}
    </div>
  );

  const { input1: setsWon1, input2: setsWon2 } = getSetsWon(match.match_sets);
  const multiSetTeam1Style = setsWon1 > setsWon2 ? winner_style : {};
  const multiSetTeam2Style = setsWon2 > setsWon1 ? winner_style : {};

  const bracket = (
    <>
      <MatchBadge match={match} theme={theme} />
      <div className={classes.top} style={isMultiSet ? multiSetTeam1Style : team1_style}>
        <Grid grow>
          <Grid.Col span={10}>{team1_label}</Grid.Col>
          <Grid.Col span={2}>
            {isMultiSet ? multiSetScores('s1') : score1}
          </Grid.Col>
        </Grid>
      </div>
      <div className={classes.divider} />
      <div className={classes.bottom} style={isMultiSet ? multiSetTeam2Style : team2_style}>
        <Grid grow>
          <Grid.Col span={10}>{team2_label}</Grid.Col>
          <Grid.Col span={2}>
            {isMultiSet ? multiSetScores('s2') : score2}
          </Grid.Col>
        </Grid>
      </div>
      {refereesEnabled && (
        <div style={{ padding: '6px 8px 0px 15px' }}>
          <RefereeDisplay
            match={match}
            refereesEnabled={refereesEnabled}
            stageItemsLookup={stageItemsLookup}
            placeholderLabel={round.lifecycle_state === 'PLACEHOLDER' ? t('tbd_label') : undefined}
          />
        </div>
      )}
    </>
  );

  if (readOnly) {
    return <div className={classes.root}>{bracket}</div>;
  }

  return (
    <>
      <UnstyledButton className={classes.root} onClick={() => setOpened(!opened)}>
        {bracket}
      </UnstyledButton>
      <MatchModal
        swrStagesResponse={assert_not_none(swrStagesResponse)}
        tournamentData={tournamentData}
        match={match}
        opened={opened}
        setOpened={setOpened}
        round={round}
      />
    </>
  );
}
