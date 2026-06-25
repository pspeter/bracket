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
  const refereesEnabled = swrInfoResponse.data?.data.referees_enabled ?? false;

  return (
    <ScoreTrackingMatchView
      swrResponse={swrResponse}
      backHref={`/score-tracking/${score_tracking_token}`}
      storageKey={`score-tracking:${score_tracking_token}:${matchId}:swapped`}
      refereesEnabled={refereesEnabled}
      saveMatch={async (next) => {
        if (score_tracking_token == null || matchId == null) return;
        // Until the score-tracking screen is migrated to per-set entry, drive the match's
        // first set (single-set matches behave exactly as before).
        const setId = swrResponse.data?.data.match_sets[0]?.id;
        if (setId == null) return;
        await updateScoreTrackingMatchSet(score_tracking_token, matchId, setId, next);
      }}
    />
  );
}
