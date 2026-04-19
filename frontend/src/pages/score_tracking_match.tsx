import { useParams } from 'react-router';

import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { updateScoreTrackingMatch } from '@services/match';
import { getScoreTrackingMatch } from '@services/score_tracking';

export default function ScoreTrackingMatchPage() {
  const { score_tracking_token, match_id } = useParams<{
    score_tracking_token: string;
    match_id: string;
  }>();
  const matchId = match_id != null ? parseInt(match_id, 10) : null;
  const swrResponse = getScoreTrackingMatch(score_tracking_token ?? null, matchId);

  return (
    <ScoreTrackingMatchView
      swrResponse={swrResponse}
      backHref={`/score-tracking/${score_tracking_token}`}
      storageKey={`score-tracking:${score_tracking_token}:${matchId}:swapped`}
      saveMatch={async (next) => {
        if (score_tracking_token == null || matchId == null) return;
        await updateScoreTrackingMatch(score_tracking_token, matchId, next);
      }}
    />
  );
}
