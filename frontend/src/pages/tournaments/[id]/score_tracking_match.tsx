import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { getTournamentIdFromRouter, responseIsValid } from '@components/utils/util';
import { getNextMatchOnCourt } from '@logic/score_tracking';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getTournamentById } from '@services/adapter';
import { endMatch, reopenMatch, scoreEditMatchSet, startMatch } from '@services/match';
import {
  getTournamentScoreTrackingInfo,
  getTournamentScoreTrackingMatch,
} from '@services/score_tracking';
import { useParams } from 'react-router';

export default function TournamentScoreTrackingMatchPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const { match_id } = useParams<{ match_id: string }>();
  const matchId = match_id != null ? parseInt(match_id, 10) : null;
  const swrResponse = getTournamentScoreTrackingMatch(tournamentData.id, matchId);
  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const swrInfoResponse = getTournamentScoreTrackingInfo(tournamentData.id, null);

  const currentMatch = swrResponse.data?.data ?? null;
  const nextMatch =
    currentMatch != null
      ? getNextMatchOnCourt(swrInfoResponse.data?.data.matches ?? [], currentMatch)
      : null;
  const nextMatchHref =
    nextMatch != null
      ? `/tournaments/${tournamentData.id}/score-tracking/matches/${nextMatch.id}`
      : null;

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      {responseIsValid(swrResponse) || swrResponse.error != null ? (
        <ScoreTrackingMatchView
          swrResponse={swrResponse}
          nextMatchHref={nextMatchHref}
          storageKey={`tournament-score-tracking:${tournamentData.id}:${matchId}:swapped`}
          refereesEnabled={swrTournamentResponse.data?.data.referees_enabled ?? false}
          actions={{
            startMatch: async () => {
              if (matchId == null) return;
              await startMatch(tournamentData.id, matchId);
            },
            endMatch: async () => {
              if (matchId == null) return;
              await endMatch(tournamentData.id, matchId);
            },
            reopenMatch: async () => {
              if (matchId == null) return;
              await reopenMatch(tournamentData.id, matchId);
            },
            scoreEdit: async (setId, body) => {
              if (matchId == null) return;
              await scoreEditMatchSet(tournamentData.id, matchId, setId, body);
            },
          }}
        />
      ) : null}
    </TournamentLayout>
  );
}
