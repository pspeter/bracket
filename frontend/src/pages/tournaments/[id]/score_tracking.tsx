import { useSearchParams } from 'react-router';

import { ScoreTrackingListView } from '@components/score_tracking/views';
import { getTournamentIdFromRouter } from '@components/utils/util';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTournamentScoreTrackingInfo } from '@services/score_tracking';

export default function TournamentScoreTrackingPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const [searchParams, setSearchParams] = useSearchParams();
  const courtIdParam = searchParams.get('court_id');
  const courtId = courtIdParam != null && courtIdParam !== '' ? Number(courtIdParam) : null;
  const swrResponse = getTournamentScoreTrackingInfo(tournamentData.id, courtId);

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
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
        getMatchHref={(matchId) =>
          `/tournaments/${tournamentData.id}/score-tracking/matches/${matchId}`
        }
        stagesHref={`/tournaments/${tournamentData.id}/stages`}
      />
    </TournamentLayout>
  );
}
