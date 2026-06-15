import {
  Badge,
  Button,
  Combobox,
  Divider,
  Group,
  InputBase,
  Modal,
  NumberInput,
  Select,
  Text,
  useCombobox,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { GiWhistle } from '@react-icons/all-files/gi/GiWhistle';
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
import { getReferees, getTeams, getTournamentById } from '@services/adapter';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { deleteMatch, updateMatch } from '@services/match';

type RefereeValue = { kind: 'team'; teamId: string } | { kind: 'name'; name: string } | null;

type MatchModalFormValues = {
  stage_item_input1_score: number;
  stage_item_input2_score: number;
  custom_duration_minutes: number | string;
  state: MatchWithDetails['state'];
  referee: RefereeValue;
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

function RefereeCombobox({
  value,
  onChange,
  teamOptions,
  recentlyUsedOptions,
}: {
  value: RefereeValue;
  onChange: (v: RefereeValue) => void;
  teamOptions: { value: string; label: string }[];
  recentlyUsedOptions: string[];
}) {
  const { t } = useTranslation();
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
  });
  const [search, setSearch] = useState('');

  const currentLabel =
    value == null
      ? ''
      : value.kind === 'team'
        ? (teamOptions.find((o) => o.value === value.teamId)?.label ?? '')
        : value.name;

  const lowerSearch = search.toLowerCase();

  const filteredTeams = teamOptions.filter((o) => o.label.toLowerCase().includes(lowerSearch));
  const filteredRecent = recentlyUsedOptions.filter((n) => n.toLowerCase().includes(lowerSearch));

  const exactMatchExists =
    teamOptions.some((o) => o.label.toLowerCase() === lowerSearch) ||
    recentlyUsedOptions.some((n) => n.toLowerCase() === lowerSearch);

  const showNewOption = search.trim().length > 0 && !exactMatchExists;

  const hasOptions = filteredTeams.length > 0 || filteredRecent.length > 0 || showNewOption;

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(val) => {
        if (val === '__clear__') {
          onChange(null);
          setSearch('');
        } else if (val.startsWith('team:')) {
          const teamId = val.slice(5);
          onChange({ kind: 'team', teamId });
          setSearch(teamOptions.find((o) => o.value === teamId)?.label ?? '');
        } else if (val.startsWith('name:')) {
          const name = val.slice(5);
          onChange({ kind: 'name', name });
          setSearch(name);
        }
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          mt="lg"
          label={t('referee_label')}
          placeholder={t('referee_placeholder')}
          leftSection={<GiWhistle size="1.1rem" />}
          rightSection={
            value != null ? (
              <Combobox.ClearButton
                onClear={() => {
                  onChange(null);
                  setSearch('');
                }}
              />
            ) : (
              <Combobox.Chevron />
            )
          }
          rightSectionPointerEvents={value != null ? 'all' : 'none'}
          value={search || currentLabel}
          onChange={(e) => {
            setSearch(e.currentTarget.value);
            combobox.openDropdown();
            combobox.updateSelectedOptionIndex();
          }}
          onClick={() => combobox.openDropdown()}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => {
            combobox.closeDropdown();
            setSearch('');
          }}
        />
      </Combobox.Target>

      <Combobox.Dropdown>
        <Combobox.Options>
          {!hasOptions && <Combobox.Empty>{t('referee_no_options')}</Combobox.Empty>}

          {filteredTeams.length > 0 && (
            <Combobox.Group label={t('referee_teams_group')}>
              {filteredTeams.map((opt) => (
                <Combobox.Option key={opt.value} value={`team:${opt.value}`}>
                  {opt.label}
                </Combobox.Option>
              ))}
            </Combobox.Group>
          )}

          {filteredRecent.length > 0 && (
            <Combobox.Group label={t('referee_recently_used_group')}>
              {filteredRecent.map((name) => (
                <Combobox.Option key={name} value={`name:${name}`}>
                  {name}
                </Combobox.Option>
              ))}
            </Combobox.Group>
          )}

          {showNewOption && (
            <Combobox.Option value={`name:${search.trim()}`}>
              {t('referee_use_as_new_name', { name: search.trim() })}
            </Combobox.Option>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
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

  const initialReferee: RefereeValue =
    match.referee?.team_id != null
      ? { kind: 'team', teamId: `${match.referee.team_id}` }
      : match.referee?.name != null
        ? { kind: 'name', name: match.referee.name }
        : null;

  const form = useForm<MatchModalFormValues>({
    initialValues: {
      stage_item_input1_score: match.stage_item_input1_score,
      stage_item_input2_score: match.stage_item_input2_score,
      custom_duration_minutes: match.custom_duration_minutes ?? match.duration_minutes,
      state: match.state,
      referee: initialReferee,
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

  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const defaultDurationMinutes =
    swrTournamentResponse.data?.data.duration_minutes ?? match.duration_minutes;
  const refereesEnabled = swrTournamentResponse.data?.data.referees_enabled ?? false;

  const swrTeamsResponse = getTeams(refereesEnabled ? tournamentData.id : undefined);
  const refereeTeamOptions = (swrTeamsResponse.data?.data.teams ?? [])
    .filter((team) => team.active)
    .map((team) => ({ value: `${team.id}`, label: team.name }));

  const swrRefereesResponse = getReferees(refereesEnabled ? tournamentData.id : undefined);
  const recentlyUsedNames = (swrRefereesResponse.data?.data ?? [])
    .filter((ref) => ref.name != null && ref.team_id == null)
    .map((ref) => ref.name as string);

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
          const referee = values.referee;

          // When referees are disabled the combobox is hidden; omit both referee
          // fields entirely so the server leaves the existing assignment untouched.
          const refereeFields = refereesEnabled
            ? {
                referee_team_id: referee?.kind === 'team' ? Number(referee.teamId) : null,
                referee_name: referee?.kind === 'name' ? referee.name : null,
              }
            : {};

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
            ...refereeFields,
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
        {refereesEnabled && (
          <RefereeCombobox
            value={form.values.referee}
            onChange={(v) => form.setFieldValue('referee', v)}
            teamOptions={refereeTeamOptions}
            recentlyUsedOptions={recentlyUsedNames}
          />
        )}
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
              form.setFieldValue('custom_duration_minutes', defaultDurationMinutes);
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
