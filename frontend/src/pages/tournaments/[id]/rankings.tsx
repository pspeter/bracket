import {
  Accordion,
  Badge,
  Button,
  Center,
  Checkbox,
  Container,
  NumberInput,
  Select,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import DeleteButton from '@components/buttons/delete';
import { EmptyTableInfo } from '@components/no_content/empty_table_info';
import RequestErrorAlert from '@components/utils/error_alert';
import { TableSkeletonSingleColumn } from '@components/utils/skeletons';
import { Translator } from '@components/utils/types';
import { getTournamentIdFromRouter } from '@components/utils/util';
import {
  Ranking,
  RankingsResponse,
  ScoringType,
  StageItemWithRounds,
  TournamentWithLevels,
} from '@openapi';
import TournamentLayout from '@pages/tournaments/_tournament_layout';
import { getRankings, getStages, getTournamentById } from '@services/adapter';
import { createRanking, deleteRanking, editRanking } from '@services/ranking';

import { getRankingTitle } from '@components/utils/rankings';

function RankingDeleteButton({
  t,
  tournament,
  ranking,
  swrRankingsResponse,
}: {
  t: Translator;
  tournament: TournamentWithLevels;
  ranking: Ranking;
  swrRankingsResponse: SWRResponse<RankingsResponse>;
}) {
  if (ranking.position === 0) {
    return (
      <Center ml="1rem" miw="10rem">
        <Badge color="indigo">{t('default_ranking_badge')}</Badge>
      </Center>
    );
  }
  return (
    <DeleteButton
      onClick={async () => {
        await deleteRanking(tournament.id, ranking.id);
        await swrRankingsResponse.mutate();
      }}
      title={t('delete_ranking_button')}
      ml="1rem"
      variant="outline"
      miw="10rem"
    />
  );
}

function EditRankingForm({
  t,
  tournament,
  ranking,
  stageItems,
  swrRankingsResponse,
}: {
  t: Translator;
  tournament: TournamentWithLevels;
  ranking: Ranking;
  stageItems: StageItemWithRounds[];
  swrRankingsResponse: SWRResponse<RankingsResponse>;
}) {
  const stageItemsForRanking = stageItems.filter((si) => si.ranking_id === ranking.id);
  const form = useForm({
    initialValues: {
      name: ranking.name ?? '',
      scoring_type: ranking.scoring_type as ScoringType,
      win_points: ranking.match_points?.win_points ?? '1.0',
      draw_points: ranking.match_points?.draw_points ?? '0.5',
      loss_points: ranking.match_points?.loss_points ?? '0.0',
      match_bonus_points: ranking.set_points_with_bonus?.match_bonus_points ?? '1.0',
      num_sets: ranking.num_sets,
      max_points: ranking.max_points,
      last_set_max_points: ranking.last_set_max_points ?? 15,
      two_point_advantage: ranking.two_point_advantage,
      position: ranking.position,
      side_switch_enabled: ranking.side_switch_every_n_points != null,
      side_switch_every_n_points: ranking.side_switch_every_n_points ?? 7,
    },
    validate: {},
  });
  const hasEvenSetsError =
    form.values.num_sets % 2 === 0 &&
    stageItemsForRanking.some((si) => si.type === 'SINGLE_ELIMINATION');
  const rankingTitle = getRankingTitle(ranking, t);

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await editRanking(
          tournament.id,
          ranking.id,
          values.scoring_type,
          values.position,
          values.side_switch_enabled ? values.side_switch_every_n_points : null,
          values.num_sets,
          values.max_points,
          values.num_sets > 2 ? values.last_set_max_points : null,
          values.two_point_advantage,
          values.name,
          values.win_points,
          values.draw_points,
          values.loss_points,
          values.match_bonus_points
        );
        await swrRankingsResponse.mutate();
      })}
    >
      <Accordion.Item key={ranking.id} value={`${ranking.position}`}>
        <Center>
          <Accordion.Control>{rankingTitle}</Accordion.Control>
          <Center>
            <RankingDeleteButton
              t={t}
              tournament={tournament}
              ranking={ranking}
              swrRankingsResponse={swrRankingsResponse}
            />
          </Center>
        </Center>
        <Accordion.Panel>
          <TextInput
            label={t('ranking_name_label')}
            placeholder={`${t('ranking_title')} ${ranking.position + 1}`}
            {...form.getInputProps('name')}
          />
          <Select
            mt="1rem"
            label={t('scoring_type_label')}
            data={[
              { value: 'MATCH_POINTS', label: t('scoring_type_match_points') },
              { value: 'SET_POINTS', label: t('scoring_type_set_points') },
              {
                value: 'SET_POINTS_WITH_MATCH_BONUS',
                label: t('scoring_type_set_points_with_match_bonus'),
              },
            ]}
            {...form.getInputProps('scoring_type')}
          />
          {form.values.scoring_type === 'MATCH_POINTS' && (
            <>
              <NumberInput
                mt="1rem"
                withAsterisk
                label={t('win_points_input_label')}
                {...form.getInputProps('win_points')}
              />
              <NumberInput
                mt="1rem"
                withAsterisk
                label={t('draw_points_input_label')}
                {...form.getInputProps('draw_points')}
              />
              <NumberInput
                mt="1rem"
                withAsterisk
                label={t('loss_points_input_label')}
                {...form.getInputProps('loss_points')}
              />
            </>
          )}
          {form.values.scoring_type === 'SET_POINTS_WITH_MATCH_BONUS' && (
            <NumberInput
              mt="1rem"
              withAsterisk
              label={t('match_bonus_points_label')}
              {...form.getInputProps('match_bonus_points')}
            />
          )}
          <NumberInput
            mt="1rem"
            withAsterisk
            min={1}
            label={t('num_sets_label')}
            {...form.getInputProps('num_sets')}
          />
          {hasEvenSetsError && (
            <Text c="red" size="sm" mt="xs">
              {t('even_sets_single_elim_error')}
            </Text>
          )}
          <NumberInput
            mt="1rem"
            withAsterisk
            min={1}
            label={t('max_points_label')}
            {...form.getInputProps('max_points')}
          />
          <Checkbox
            mt="lg"
            label={t('two_point_advantage_label')}
            {...form.getInputProps('two_point_advantage', { type: 'checkbox' })}
          />
          {form.values.num_sets > 2 && (
            <NumberInput
              mt="1rem"
              withAsterisk
              min={1}
              label={t('last_set_max_points_label')}
              {...form.getInputProps('last_set_max_points')}
            />
          )}
          <Checkbox
            mt="lg"
            label={t('side_switch_reminder_enabled_label')}
            {...form.getInputProps('side_switch_enabled', { type: 'checkbox' })}
          />
          {form.values.side_switch_enabled && (
            <NumberInput
              mt="sm"
              withAsterisk
              min={1}
              label={t('side_switch_every_n_points_label')}
              {...form.getInputProps('side_switch_every_n_points')}
            />
          )}
          <Button
            fullWidth
            style={{ marginTop: 16 }}
            color="green"
            type="submit"
            disabled={hasEvenSetsError}
          >
            {`${t('save_button')} ${rankingTitle}`}
          </Button>
        </Accordion.Panel>
      </Accordion.Item>
    </form>
  );
}

function RankingForm({
  t,
  tournament,
  stageItems,
  swrRankingsResponse,
}: {
  t: Translator;
  tournament: TournamentWithLevels;
  stageItems: StageItemWithRounds[];
  swrRankingsResponse: SWRResponse<RankingsResponse>;
}) {
  const rankings: Ranking[] = swrRankingsResponse.data != null ? swrRankingsResponse.data.data : [];

  const rows = rankings
    .sort((s1: Ranking, s2: Ranking) => s1.position - s2.position)
    .map((ranking) => (
      <EditRankingForm
        t={t}
        tournament={tournament}
        ranking={ranking}
        stageItems={stageItems}
        swrRankingsResponse={swrRankingsResponse}
      />
    ));

  if (swrRankingsResponse.isLoading) {
    return <TableSkeletonSingleColumn />;
  }

  if (swrRankingsResponse.error) return <RequestErrorAlert error={swrRankingsResponse.error} />;

  if (rows.length < 1) return <EmptyTableInfo entity_name={t('rankings_title')} />;

  return (
    <Accordion multiple defaultValue={['0']}>
      {rows}
    </Accordion>
  );
}

export default function RankingsPage() {
  const { tournamentData } = getTournamentIdFromRouter();
  const swrRankingsResponse = getRankings(tournamentData.id);
  const swrStagesResponse = getStages(tournamentData.id);

  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const tournamentDataFull = swrTournamentResponse.data?.data;
  const stageItems = (swrStagesResponse.data?.data ?? []).flatMap((s) => s.stage_items);
  const { t } = useTranslation();

  // TODO: show loading icon.
  if (tournamentDataFull == null) {
    return null;
  }

  return (
    <TournamentLayout tournament_id={tournamentData.id}>
      <Container maw="50rem">
        <RankingForm
          t={t}
          tournament={tournamentDataFull}
          stageItems={stageItems}
          swrRankingsResponse={swrRankingsResponse}
        />
        <Button
          fullWidth
          mt="1rem"
          color="green"
          variant="outline"
          onClick={async () => {
            await createRanking(tournamentDataFull.id);
            await swrRankingsResponse.mutate();
          }}
        >
          {t('add_ranking_button')}
        </Button>
      </Container>
    </TournamentLayout>
  );
}
