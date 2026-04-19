import { ScoreTrackingListView } from '@components/score_tracking/views';
import { getTournamentIdFromRouter } from '@components/utils/util';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTournamentScoreTrackingInfo } from '@services/score_tracking';

export default function TournamentScoreTrackingPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const swrResponse = getTournamentScoreTrackingInfo(tournamentData.id);

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <ScoreTrackingListView
        swrResponse={swrResponse}
        getMatchHref={(matchId) =>
          `/tournaments/${tournamentData.id}/score-tracking/matches/${matchId}`
        }
      />
    </TournamentLayout>
  );
}
