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
  Stack,
  Text,
  useCombobox,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { GiWhistle } from '@react-icons/all-files/gi/GiWhistle';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { ConfirmModal } from '@components/modals/confirm_modal';
import { formatMatchInput1, formatMatchInput2 } from '@components/utils/match';
import { formatStageItemInput } from '@components/utils/stage_item_input';
import { TournamentMinimal } from '@components/utils/tournament';
import { CONFLICT_COLOURS, levelSwatchColour } from '@logic/colors';
import { computeConflictFlags } from '@logic/planning/conflicts';
import {
  LevelResponse,
  MatchWithDetails,
  RoundWithMatches,
  StagesWithStageItemsResponse,
} from '@openapi';
import { getReferees, getTournamentById } from '@services/adapter';
import { getMatchLookup, getStageItemLookup } from '@services/lookups';
import { resetMatch, updateMatch, updateMatchSet } from '@services/match';

type RefereeValue = { kind: 'slot'; inputId: string } | { kind: 'name'; name: string } | null;

type SetFormValue = {
  id: number;
  set_number: number;
  stage_item_input1_score: number;
  stage_item_input2_score: number;
  state: MatchWithDetails['match_sets'][number]['state'];
};

type MatchModalFormValues = {
  sets: SetFormValue[];
  custom_duration_minutes: number | string;
  referee: RefereeValue;
};

function RefereeCombobox({
  value,
  onChange,
  slotOptions,
  recentlyUsedOptions,
}: {
  value: RefereeValue;
  onChange: (v: RefereeValue) => void;
  slotOptions: { value: string; label: string }[];
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
      : value.kind === 'slot'
        ? (slotOptions.find((o) => o.value === value.inputId)?.label ?? '')
        : value.name;

  const lowerSearch = search.toLowerCase();

  const filteredSlots = slotOptions.filter((o) => o.label.toLowerCase().includes(lowerSearch));
  const filteredRecent = recentlyUsedOptions.filter((n) => n.toLowerCase().includes(lowerSearch));

  const exactMatchExists =
    slotOptions.some((o) => o.label.toLowerCase() === lowerSearch) ||
    recentlyUsedOptions.some((n) => n.toLowerCase() === lowerSearch);

  const showNewOption = search.trim().length > 0 && !exactMatchExists;

  const hasOptions = filteredSlots.length > 0 || filteredRecent.length > 0 || showNewOption;

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(val) => {
        if (val === '__clear__') {
          onChange(null);
          setSearch('');
        } else if (val.startsWith('slot:')) {
          const inputId = val.slice(5);
          onChange({ kind: 'slot', inputId });
          setSearch(slotOptions.find((o) => o.value === inputId)?.label ?? '');
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

          {filteredSlots.length > 0 && (
            <Combobox.Group label={t('referee_slots_group')}>
              {filteredSlots.map((opt) => (
                <Combobox.Option key={opt.value} value={`slot:${opt.value}`}>
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
  setOpened,
  round,
  levels,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  setOpened: any;
  round: RoundWithMatches | null;
  levels?: LevelResponse[];
}) {
  if (match == null) {
    return null;
  }

  const { t } = useTranslation();

  const initialReferee: RefereeValue =
    match.referee_stage_item_input_id != null
      ? { kind: 'slot', inputId: `${match.referee_stage_item_input_id}` }
      : match.referee_name != null
        ? { kind: 'name', name: match.referee_name }
        : null;

  const form = useForm<MatchModalFormValues>({
    initialValues: {
      sets: match.match_sets.map((set) => ({
        id: set.id,
        set_number: set.set_number,
        stage_item_input1_score: set.stage_item_input1_score,
        stage_item_input2_score: set.stage_item_input2_score,
        state: set.state,
      })),
      custom_duration_minutes: match.custom_duration_minutes ?? match.duration_minutes,
      referee: initialReferee,
    },

    validate: {
      sets: {
        stage_item_input1_score: (value) => (value >= 0 ? null : t('negative_score_validation')),
        stage_item_input2_score: (value) => (value >= 0 ? null : t('negative_score_validation')),
      },
      custom_duration_minutes: (value) => {
        const numericValue = Number(value);
        return Number.isFinite(numericValue) && numericValue >= 0
          ? null
          : t('negative_match_duration_validation');
      },
    },
  });

  const [durationIsCustom, setDurationIsCustom] = useState(match.custom_duration_minutes != null);
  const [resetModalOpened, setResetModalOpened] = useState(false);

  const swrTournamentResponse = getTournamentById(tournamentData.id);
  const defaultDurationMinutes =
    swrTournamentResponse.data?.data.duration_minutes ?? match.duration_minutes;
  const refereesEnabled = swrTournamentResponse.data?.data.referees_enabled ?? false;

  const swrRefereesResponse = getReferees(refereesEnabled ? tournamentData.id : undefined);
  const recentlyUsedNames = swrRefereesResponse.data?.data ?? [];

  const stageItemsLookup = getStageItemLookup(swrStagesResponse);
  const matchesLookup = getMatchLookup(swrStagesResponse);
  const matchEntry = matchesLookup[match.id];
  const matchLevelId = matchEntry?.stage.level_id ?? match.level_id;
  const level = levels?.find((candidate) => candidate.id === matchLevelId) ?? null;

  // Referee slots are the stage-item inputs in the match's own stage (concrete teams, "Winner of
  // Group A" placeholders, and still-empty positions), mirroring how playing slots are picked.
  // Slots are restricted to the match's stage — not just its level — because a later stage's slot
  // names a participant who is still unknown while this match is played; the backend enforces the
  // same rule (see eligible_referee_slot_ids).
  const matchStageId = matchEntry?.stage.id;
  const ownInputIds = new Set(
    [match.stage_item_input1_id, match.stage_item_input2_id].filter((id) => id != null)
  );
  const refereeSlotOptions = refereesEnabled
    ? (swrStagesResponse.data?.data ?? [])
        .filter((stage) => stage.id === matchStageId)
        .flatMap((stage) => stage.stage_items)
        .flatMap((stageItem) => stageItem.inputs)
        .filter((input) => !ownInputIds.has(input.id))
        .map((input) => ({
          value: `${input.id}`,
          label: formatStageItemInput(input, stageItemsLookup) ?? t('empty_slot'),
        }))
    : [];
  const contextColour =
    level != null && levels != null ? levelSwatchColour(level.id, levels) : 'gray';
  const isRoundRobin = matchEntry?.stageItem.type === 'ROUND_ROBIN';
  const contextBadges = [
    level != null ? { label: t('match_context_level_label'), value: level.name } : null,
    matchEntry != null
      ? { label: t('match_context_stage_label'), value: matchEntry.stage.name }
      : null,
    matchEntry != null
      ? { label: t('match_context_stage_item_label'), value: matchEntry.stageItem.name }
      : null,
    matchEntry != null && isRoundRobin
      ? {
          label: t('match_context_match_label'),
          value: t('match_context_match_number', { number: matchEntry.matchNumber }),
        }
      : null,
    matchEntry != null && !isRoundRobin
      ? {
          label: t('match_context_round_label'),
          value: t('match_context_round_number', { number: matchEntry.roundNumber }),
        }
      : null,
  ].filter((badge): badge is { label: string; value: string } => badge != null);

  const team1Name = formatMatchInput1(t, stageItemsLookup, matchesLookup, match);
  const team2Name = formatMatchInput2(t, stageItemsLookup, matchesLookup, match);

  // Conflict flags are derived client-side from the current schedule with the same engine
  // the planner grid uses, so the modal and the grid always agree — and update together on
  // an optimistic move — instead of reading the backend-persisted columns.
  const marginMinutes = swrTournamentResponse.data?.data.margin_minutes ?? 0;
  const conflictFlags = useMemo(
    () =>
      computeConflictFlags(swrStagesResponse.data?.data ?? [], marginMinutes, { refereesEnabled }),
    [swrStagesResponse.data?.data, marginMinutes, refereesEnabled]
  );
  const conflicts = conflictFlags.get(match.id);

  // Surface the same scheduling conflicts the planner grid flags on this match, each as an
  // icon plus a brief description. Colours come from the shared CONFLICT_COLOURS so the
  // grid and this list always agree.
  type ActiveConflict = { key: string; colour: string; label: string };
  const activeConflicts: (ActiveConflict | null)[] = [
    conflicts?.stage_item_input1_conflict
      ? {
          key: 'input1',
          colour: CONFLICT_COLOURS.teamDoubleBooked,
          label: t('team_double_booked_conflict_label', { team: team1Name }),
        }
      : null,
    conflicts?.stage_item_input2_conflict
      ? {
          key: 'input2',
          colour: CONFLICT_COLOURS.teamDoubleBooked,
          label: t('team_double_booked_conflict_label', { team: team2Name }),
        }
      : null,
    conflicts?.precedence_conflict
      ? {
          key: 'precedence',
          colour: CONFLICT_COLOURS.precedence,
          label: t('precedence_conflict_label'),
        }
      : null,
    conflicts?.feeder_precedence_conflict
      ? {
          key: 'feeder_precedence',
          colour: CONFLICT_COLOURS.precedence,
          label: t('feeder_precedence_conflict_label'),
        }
      : null,
    conflicts?.round_order_conflict
      ? {
          key: 'round_order',
          colour: CONFLICT_COLOURS.roundOrder,
          label: t('round_order_conflict_label'),
        }
      : null,
    conflicts?.short_break_conflict
      ? {
          key: 'short_break',
          colour: CONFLICT_COLOURS.shortBreak,
          label: t('short_break_conflict_label'),
        }
      : null,
    refereesEnabled && conflicts?.referee_conflict
      ? {
          key: 'referee',
          colour: CONFLICT_COLOURS.referee,
          label: t('referee_conflict_label'),
        }
      : null,
  ];
  const shownConflicts = activeConflicts.filter(
    (conflict): conflict is ActiveConflict => conflict != null
  );

  return (
    <>
      <form
        onSubmit={form.onSubmit(async (values) => {
          const referee = values.referee;

          // When referees are disabled the combobox is hidden; omit both referee
          // fields entirely so the server leaves the existing assignment untouched.
          const refereeFields = refereesEnabled
            ? {
                referee_stage_item_input_id:
                  referee?.kind === 'slot' ? Number(referee.inputId) : null,
                referee_name: referee?.kind === 'name' ? referee.name : null,
              }
            : {};

          // Persist each changed set one at a time so the ranking recalculation the backend
          // runs per set never races with the next write.
          for (let i = 0; i < values.sets.length; i += 1) {
            const set = values.sets[i];
            const initial = match.match_sets[i];
            const changed =
              initial == null ||
              set.stage_item_input1_score !== initial.stage_item_input1_score ||
              set.stage_item_input2_score !== initial.stage_item_input2_score ||
              set.state !== initial.state;
            if (changed) {
              // eslint-disable-next-line no-await-in-loop
              await updateMatchSet(tournamentData.id, match.id, set.id, {
                stage_item_input1_score: set.stage_item_input1_score,
                stage_item_input2_score: set.stage_item_input2_score,
                state: set.state,
              });
            }
          }

          const updatedMatch = {
            id: match.id,
            round_id: match.round_id,
            court_id: match.court_id || null,
            custom_duration_minutes: durationIsCustom
              ? Number(values.custom_duration_minutes)
              : null,
            ...refereeFields,
          };
          await updateMatch(tournamentData.id, match.id, updatedMatch);
          await swrStagesResponse.mutate();
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
        {shownConflicts.length > 0 && (
          <Stack gap={6} mb="md">
            <Text size="sm" fw={600}>
              {t('active_conflicts_label')}
            </Text>
            {shownConflicts.map((conflict) => (
              <Group key={conflict.key} gap="xs" wrap="nowrap" align="center">
                <AiFillWarning color={conflict.colour} style={{ flexShrink: 0 }} />
                <Text size="sm" c="dimmed">
                  {conflict.label}
                </Text>
              </Group>
            ))}
          </Stack>
        )}
        <Stack gap="md">
          {form.values.sets.map((set, index) => (
            <Stack key={set.id} gap={6}>
              {form.values.sets.length > 1 && (
                <Text size="sm" fw={600}>
                  {t('set_label', { number: set.set_number })}
                </Text>
              )}
              <Group grow align="start" wrap="nowrap">
                <NumberInput
                  withAsterisk
                  label={`${t('score_of_label')} ${team1Name}`}
                  placeholder={`${t('score_of_label')} ${team1Name}`}
                  {...form.getInputProps(`sets.${index}.stage_item_input1_score`)}
                />
                <NumberInput
                  withAsterisk
                  label={`${t('score_of_label')} ${team2Name}`}
                  placeholder={`${t('score_of_label')} ${team2Name}`}
                  {...form.getInputProps(`sets.${index}.stage_item_input2_score`)}
                />
              </Group>
              <Select
                label={
                  form.values.sets.length > 1
                    ? t('set_state_label', { number: set.set_number })
                    : t('match_state_label')
                }
                data={[
                  { value: 'NOT_STARTED', label: t('match_state_not_started') },
                  { value: 'IN_PROGRESS', label: t('match_state_in_progress') },
                  { value: 'COMPLETED', label: t('match_state_completed') },
                ]}
                {...form.getInputProps(`sets.${index}.state`)}
                onChange={(value) => {
                  if (value != null) {
                    form.setFieldValue(`sets.${index}.state`, value as SetFormValue['state']);
                    if (value === 'NOT_STARTED') {
                      form.setFieldValue(`sets.${index}.stage_item_input1_score`, 0);
                      form.setFieldValue(`sets.${index}.stage_item_input2_score`, 0);
                    }
                  }
                }}
              />
            </Stack>
          ))}
        </Stack>
        {refereesEnabled && (
          <RefereeCombobox
            value={form.values.referee}
            onChange={(v) => form.setFieldValue('referee', v)}
            slotOptions={refereeSlotOptions}
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
        <Button
          fullWidth
          style={{ marginTop: 12 }}
          color="red"
          variant="light"
          onClick={() => setResetModalOpened(true)}
        >
          {t('reset_match_button')}
        </Button>
      </form>
      <ConfirmModal
        opened={resetModalOpened}
        setOpened={setResetModalOpened}
        title={t('reset_match_modal_title')}
        message={t('reset_match_modal_message')}
        confirmLabel={t('reset_match_button')}
        onConfirm={async () => {
          await resetMatch(tournamentData.id, match.id);
          await swrStagesResponse.mutate();
          setOpened(false);
        }}
      />
    </>
  );
}

export default function MatchModal({
  tournamentData,
  match,
  swrStagesResponse,
  opened,
  setOpened,
  round,
  levels,
}: {
  tournamentData: TournamentMinimal;
  match: MatchWithDetails | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
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
