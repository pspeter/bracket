import { useParams } from 'react-router';

import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { updateScoreTrackingMatchSet } from '@services/match';
import { getScoreTrackingInfo, getScoreTrackingMatch } from '@services/score_tracking';

export default function ScoreTrackingMatchPage() {
  const { score_tracking_token, match_id } = useParams<{
    score_tracking_token: string;
    match_id: string;
  }>();
  const matchId = match_id != null ? parseInt(match_id, 10) : null;
  const swrResponse = getScoreTrackingMatch(score_tracking_token ?? null, matchId);
  const swrInfoResponse = getScoreTrackingInfo(score_tracking_token ?? null, null);
  const tournamentId = swrInfoResponse.data?.data.tournament_id ?? null;
  const refereesEnabled = swrInfoResponse.data?.data.referees_enabled ?? false;

  return (
    <ScoreTrackingMatchView
      swrResponse={swrResponse}
      backHref={`/score-tracking/${score_tracking_token}`}
      storageKey={`score-tracking:${score_tracking_token}:${matchId}:swapped`}
      refereesEnabled={refereesEnabled}
      updateSet={async (setId, body) => {
        if (score_tracking_token == null || matchId == null) return;
        await updateScoreTrackingMatchSet(score_tracking_token, tournamentId, matchId, setId, body);
      }}
    />
  );
}
