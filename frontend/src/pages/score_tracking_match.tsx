import { useParams } from 'react-router';

import { ScoreTrackingMatchView } from '@components/score_tracking/views';
import { getNextMatchOnCourt } from '@logic/score_tracking';
import {
  endScoreTrackingMatch,
  reopenScoreTrackingMatch,
  scoreEditScoreTrackingMatchSet,
  startScoreTrackingMatch,
} from '@services/match';
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

  const currentMatch = swrResponse.data?.data ?? null;
  const nextMatch =
    currentMatch != null
      ? getNextMatchOnCourt(swrInfoResponse.data?.data.matches ?? [], currentMatch)
      : null;
  const nextMatchHref =
    nextMatch != null ? `/score-tracking/${score_tracking_token}/matches/${nextMatch.id}` : null;

  return (
    <ScoreTrackingMatchView
      swrResponse={swrResponse}
      nextMatchHref={nextMatchHref}
      storageKey={`score-tracking:${score_tracking_token}:${matchId}:swapped`}
      refereesEnabled={refereesEnabled}
      actions={{
        startMatch: async () => {
          if (score_tracking_token == null || matchId == null) return;
          await startScoreTrackingMatch(score_tracking_token, tournamentId, matchId);
        },
        endMatch: async () => {
          if (score_tracking_token == null || matchId == null) return;
          await endScoreTrackingMatch(score_tracking_token, tournamentId, matchId);
        },
        reopenMatch: async () => {
          if (score_tracking_token == null || matchId == null) return;
          await reopenScoreTrackingMatch(score_tracking_token, tournamentId, matchId);
        },
        scoreEdit: async (setId, body) => {
          if (score_tracking_token == null || matchId == null) return;
          await scoreEditScoreTrackingMatchSet(
            score_tracking_token,
            tournamentId,
            matchId,
            setId,
            body
          );
        },
      }}
    />
  );
}
