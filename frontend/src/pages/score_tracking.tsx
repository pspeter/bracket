import { useParams, useSearchParams } from 'react-router';

import { ScoreTrackingListView } from '@components/score_tracking/views';
import { getScoreTrackingInfo } from '@services/score_tracking';

export default function ScoreTrackingPage() {
  const { score_tracking_token } = useParams<{ score_tracking_token: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const courtIdParam = searchParams.get('court_id');
  const courtId = courtIdParam != null && courtIdParam !== '' ? Number(courtIdParam) : null;
  const swrResponse = getScoreTrackingInfo(score_tracking_token ?? null, courtId);

  return (
    <ScoreTrackingListView
      swrResponse={swrResponse}
      courtId={courtId}
      onCourtIdChange={(nextCourtId) => {
        const next = new URLSearchParams(searchParams);
        if (nextCourtId == null) {
          next.delete('court_id');
        } else {
          next.set('court_id', `${nextCourtId}`);
        }
        setSearchParams(next);
      }}
      getMatchHref={(matchId) => `/score-tracking/${score_tracking_token}/matches/${matchId}`}
    />
  );
}
