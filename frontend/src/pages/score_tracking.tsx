import { useParams } from 'react-router';

import { ScoreTrackingListView } from '@components/score_tracking/views';
import { getScoreTrackingInfo } from '@services/score_tracking';

export default function ScoreTrackingPage() {
  const { score_tracking_token } = useParams<{ score_tracking_token: string }>();
  const swrResponse = getScoreTrackingInfo(score_tracking_token ?? null);

  return (
    <ScoreTrackingListView
      swrResponse={swrResponse}
      getMatchHref={(matchId) => `/score-tracking/${score_tracking_token}/matches/${matchId}`}
    />
  );
}
