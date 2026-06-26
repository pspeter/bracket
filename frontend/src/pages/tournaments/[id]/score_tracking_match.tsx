import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTournamentById } from '@services/adapter';
import { updateMatchSet } from '@services/match';
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
          refereesEnabled={swrTournamentResponse.data?.data.referees_enabled ?? false}
          saveMatch={async (next) => {
            if (matchId == null) return;
            // Drive the match's first set; single-set matches behave exactly as before.
            const setId = swrResponse.data?.data.match_sets[0]?.id;
            if (setId == null) return;
            await updateMatchSet(tournamentData.id, matchId, setId, next);
          }}
        />
      ) : null}
    </TournamentLayout>
  );
}
