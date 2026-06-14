import { Badge, Button, Divider, Group, Modal, NumberInput, Select, Text } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import DeleteButton from '@components/buttons/delete';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { TournamentMinimal } from '@components/utils/tournament';
import { levelSwatchColour } from '@logic/colors';
import {
  LevelResponse,
  MatchWithDetails,
  RoundWithMatches,
  StagesWithStageItemsResponse,
} from '@openapi';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { deleteMatch, updateMatch } from '@services/match';

type MatchModalFormValues = {
  stage_item_input1_score: number;
  stage_item_input2_score: number;
  custom_duration_minutes: number | string;
  state: MatchWithDetails['state'];
};

function MatchDeleteButton({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
}) {
  const { t } = useTranslation();
  return (
    <DeleteButton
      fullWidth
      onClick={async () => {
        await deleteMatch(tournamentData.id, match.id);
        await swrStagesResponse.mutate();
        if (swrUpcomingMatchesResponse != null) await swrUpcomingMatchesResponse.mutate();
      }}
      style={{ marginTop: '1rem' }}
      size="sm"
      title={t('remove_match_button')}
    />
  );
}

function MatchModalForm({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  setOpened,
  round,
  levels,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  setOpened: any;
  round: RoundWithMatches | null;
  levels?: LevelResponse[];
}) {
  if (match == null) {
    return null;
  }

  const { t } = useTranslation();
  const form = useForm<MatchModalFormValues>({
    initialValues: {
      stage_item_input1_score: match.stage_item_input1_score,
      stage_item_input2_score: match.stage_item_input2_score,
      custom_duration_minutes: match.custom_duration_minutes ?? match.duration_minutes,
      state: match.state,
    },

    validate: {
      stage_item_input1_score: (value) => (value >= 0 ? null : t('negative_score_validation')),
      stage_item_input2_score: (value) => (value >= 0 ? null : t('negative_score_validation')),
      custom_duration_minutes: (value) => {
        const numericValue = Number(value);
        return Number.isFinite(numericValue) && numericValue >= 0
          ? null
          : t('negative_match_duration_validation');
      },
    },
  });

  const [durationIsCustom, setDurationIsCustom] = useState(match.custom_duration_minutes != null);

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);
  const matchEntry = matchesLookup[match.id];
  const level =
    levels?.find((candidate) => candidate.id === (matchEntry?.stage.level_id ?? match.level_id)) ??
    null;
  const contextColour =
    level != null && levels != null ? levelSwatchColour(level.id, levels) : 'gray';
  const contextBadges = [
    level != null ? { label: t('match_context_level_label'), value: level.name } : null,
    matchEntry != null
      ? { label: t('match_context_stage_label'), value: matchEntry.stage.name }
      : null,
    matchEntry != null
      ? { label: t('match_context_stage_item_label'), value: matchEntry.stageItem.name }
      : null,
    matchEntry != null
      ? {
          label: t('match_context_match_label'),
          value: t('match_context_match_number', { number: matchEntry.matchNumber }),
        }
      : null,
  ].filter((badge): badge is { label: string; value: string } => badge != null);

  const team1Name = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  const team2Name = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);

  return (
    <>
      <form
        onSubmit={form.onSubmit(async (values) => {
          const updatedMatch = {
            id: match.id,
            round_id: match.round_id,
            stage_item_input1_score: values.stage_item_input1_score,
            stage_item_input2_score: values.stage_item_input2_score,
            court_id: match.court_id || null,
            custom_duration_minutes: durationIsCustom
              ? Number(values.custom_duration_minutes)
              : null,
            state: values.state,
            completed_at: match.completed_at,
          };
          await updateMatch(tournamentData.id, match.id, updatedMatch);
          await swrStagesResponse.mutate();
          if (swrUpcomingMatchesResponse != null) await swrUpcomingMatchesResponse.mutate();
          setOpened(false);
        })}
      >
        {contextBadges.length > 0 && (
          <Group gap="xs" mb="md">
            {contextBadges.map((badge) => (
              <Badge
                key={badge.label}
                color={contextColour}
                variant="light"
                aria-label={`${badge.label}: ${badge.value}`}
              >
                {badge.value}
              </Badge>
            ))}
          </Group>
        )}
        <NumberInput
          withAsterisk
          label={`${t('score_of_label')} ${team1Name}`}
          placeholder={`${t('score_of_label')} ${team1Name}`}
          disabled={form.values.state !== 'IN_PROGRESS'}
          {...form.getInputProps('stage_item_input1_score')}
        />
        <NumberInput
          withAsterisk
          mt="lg"
          label={`${t('score_of_label')} ${team2Name}`}
          placeholder={`${t('score_of_label')} ${team2Name}`}
          disabled={form.values.state !== 'IN_PROGRESS'}
          {...form.getInputProps('stage_item_input2_score')}
        />
        <Select
          mt="lg"
          label={t('match_state_label')}
          data={[
            { value: 'NOT_STARTED', label: t('match_state_not_started') },
            { value: 'IN_PROGRESS', label: t('match_state_in_progress') },
            { value: 'COMPLETED', label: t('match_state_completed') },
          ]}
          {...form.getInputProps('state')}
        />
        <Divider mt="lg" />

        <Text size="sm" mt="lg">
          {t('match_duration_label')}
        </Text>
        <Group align="end" wrap="nowrap">
          <NumberInput
            style={{ flex: 1 }}
            rightSection={<Text>{t('minutes')}</Text>}
            rightSectionWidth={92}
            {...form.getInputProps('custom_duration_minutes')}
            onChange={(value) => {
              form.setFieldValue('custom_duration_minutes', value);
              setDurationIsCustom(true);
            }}
          />
          <Button
            variant="light"
            disabled={!durationIsCustom}
            onClick={() => {
              form.setFieldValue('custom_duration_minutes', match.duration_minutes);
              setDurationIsCustom(false);
            }}
          >
            {t('set_default_duration_button')}
          </Button>
        </Group>

        <Button fullWidth style={{ marginTop: 20 }} color="green" type="submit">
          {t('save_button')}
        </Button>
      </form>
      {round && round.is_draft && (
        <MatchDeleteButton
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
          tournamentData={tournamentData}
          match={match}
        />
      )}
    </>
  );
}

export default function MatchModal({
  tournamentData,
  match,
  swrStagesResponse,
  swrUpcomingMatchesResponse,
  opened,
  setOpened,
  round,
  levels,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrUpcomingMatchesResponse: SWRResponse | null;
  opened: boolean;
  setOpened: any;
  round: RoundWithMatches | null;
  levels?: LevelResponse[];
}) {
  const { t } = useTranslation();

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={t('edit_match_modal_title')}>
        <MatchModalForm
          key={match?.id ?? 'no-match'}
          swrStagesResponse={swrStagesResponse}
          swrUpcomingMatchesResponse={swrUpcomingMatchesResponse}
          tournamentData={tournamentData}
          match={match}
          setOpened={setOpened}
          round={round}
          levels={levels}
        />
      </Modal>
    </>
  );
}
