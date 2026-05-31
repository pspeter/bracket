import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTournamentById } from '@services/adapter';
import { updateTournamentScoreTrackingMatch } from '@services/match';
import { getTournamentScoreTrackingMatch } from '@services/score_tracking';
import { useParams } from 'react-router';

export default function TournamentScoreTrackingMatchPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const { match_id } = useParams<{ match_id: string }>();
  const matchId = match_id != null ? parseInt(match_id, 10) : null;
  const swrResponse = getTournamentScoreTrackingMatch(tournamentData.id, matchId);
  const swrTournamentResponse = getTournamentById(tournamentData.id);

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      {responseIsValid(swrResponse) || swrResponse.error != null ? (
        <ScoreTrackingMatchView
          swrResponse={swrResponse}
          backHref={`/tournaments/${tournamentData.id}/score-tracking`}
          storageKey={`tournament-score-tracking:${tournamentData.id}:${matchId}:swapped`}
          levels={swrTournamentResponse.data?.data.levels ?? []}
          saveMatch={async (next) => {
            if (matchId == null) return;
            await updateTournamentScoreTrackingMatch(tournamentData.id, matchId, next);
          }}
        />
      ) : null}
    </TournamentLayout>
  );
}
