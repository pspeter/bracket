import {
  ActionIcon,
  Badge,
  Card,
  CheckIcon,
  Combobox,
  Divider,
  Group,
  InputBase,
  Menu,
  Stack,
  Text,
  Tooltip,
  useCombobox,
  useMantineTheme,
} from '@mantine/core';
import { useColorScheme } from '@mantine/hooks';
import { AiFillWarning } from '@react-icons/all-files/ai/AiFillWarning';
import { BiCheck } from '@react-icons/all-files/bi/BiCheck';
import {
  IconArrowsShuffle,
  IconDots,
  IconListNumbers,
  IconPencil,
  IconTrash,
} from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BiSolidWrench } from 'react-icons/bi';
import { SWRResponse } from 'swr';

import CreateStageButton from '@components/buttons/create_stage';
import { LevelBadge } from '@components/levels/levels';
import { ConfirmModal } from '@components/modals/confirm_modal';
import { CreateFromTemplateButton } from '@components/modals/create_from_template_modal';
import { CreateStageItemModal } from '@components/modals/create_stage_item';
import { SetStageRankingModal } from '@components/modals/set_stage_ranking';
import { UpdateStageModal } from '@components/modals/update_stage';
import { UpdateStageItemModal } from '@components/modals/update_stage_item';
import { assert_not_none } from '@components/utils/assert';
import RequestErrorAlert from '@components/utils/error_alert';
import PreloadLink from '@components/utils/link';
import {
  StageItemInput,
  StageItemInputChoice,
  StageItemInputOption,
  formatStageItemInputTentative,
} from '@components/utils/stage_item_input';
import {
  FullTeamWithPlayers,
  LevelResponse,
  Ranking,
  StageItemInputOptionsResponse,
  StageItemWithRounds,
  StageWithStageItems,
  StagesWithStageItemsResponse,
  TournamentWithLevels,
} from '@openapi';
import { getAssignedTeamIds, getStageItemLookup, getTeamsLookup } from '@services/lookups';
import { deleteStage } from '@services/stage';
import { deleteStageItem } from '@services/stage_item';
import { updateStageItemInput } from '@services/stage_item_input';

function StageItemInputComboBox({
  tournament,
  stageItemInput,
  current_key,
  availableInputs,
  swrAvailableInputsResponse,
  swrStagesResponse,
}: {
  tournament: TournamentWithLevels;
  stageItemInput: StageItemInput;
  current_key: string | null;
  availableInputs: StageItemInputChoice[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const { t } = useTranslation();
  const [selectedInput, setSelectedInput] = useState<StageItemInputChoice | null>(
    availableInputs.find((o) => o.value === current_key) || null
  );
  const [successIcon, setSuccessIcon] = useState<boolean>(false);

  useEffect(() => {
    setSelectedInput(availableInputs.find((o) => o.value === current_key) ?? null);
  }, [current_key, swrAvailableInputsResponse.data, swrStagesResponse.data]);
  const [search, setSearch] = useState('');
  const combobox = useCombobox({
    onDropdownClose: () => {
      combobox.resetSelectedOption();
      combobox.focusTarget();
      setSearch('');
    },

    onDropdownOpen: () => {
      combobox.focusSearchInput();
    },
  });

  const options = availableInputs
    .filter((option: StageItemInputChoice) => !option.already_taken)
    .filter((item) => (item.label || 'None').toLowerCase().includes(search.toLowerCase().trim()))
    .map((option: StageItemInputChoice, i: number) => (
      <Combobox.Option key={i} value={option.value}>
        <Group gap="xs" justify="space-between">
          <Group gap="xs">
            {option.label || <i>None</i>}
            {option.team_id != null ? (
              <LevelBadge levels={tournament.levels} levelId={option.team_level_id} />
            ) : null}
          </Group>
          {option.value === selectedInput?.value && <CheckIcon size={12} />}
        </Group>
      </Combobox.Option>
    ));

  const theme = useMantineTheme();
  const dropdownBorderColor = useColorScheme() === 'dark' ? '#444' : '#ccc';

  return (
    <Combobox
      shadow="lg"
      store={combobox}
      onOptionSubmit={(val) => {
        const option = availableInputs.find((o) => o.value === val) || null;
        setSelectedInput(option);
        updateStageItemInput(
          tournament.id,
          stageItemInput.stage_item_id,
          stageItemInput.id,
          option?.team_id || null,
          option?.winner_position || null,
          option?.winner_from_stage_item_id || null
        ).then(() => {
          swrAvailableInputsResponse.mutate();
          swrStagesResponse.mutate();

          setSuccessIcon(true);

          setTimeout(() => {
            setSuccessIcon(false);
          }, 1500);
        });
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          radius="0.5rem"
          component="button"
          type="button"
          rightSection={successIcon ? <BiCheck size={18} color={theme.colors.green[4]} /> : null}
          pointer
          rightSectionPointerEvents="none"
          onClick={() => combobox.toggleDropdown()}
        >
          {selectedInput?.label ? (
            <Group gap="xs">
              {selectedInput.label}
              {selectedInput.team_id != null ? (
                <LevelBadge levels={tournament.levels} levelId={selectedInput.team_level_id} />
              ) : null}
            </Group>
          ) : (
            <Group gap="xs">
              <AiFillWarning size={18} color={theme.colors.orange[4]} />
              <b>{selectedInput?.label || t('empty_slot').toUpperCase()}</b>
            </Group>
          )}
        </InputBase>
      </Combobox.Target>

      <Combobox.Dropdown style={{ border: `solid 0.1rem ${dropdownBorderColor}` }}>
        <Combobox.Search
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          placeholder={t('search_placeholder')}
        />
        <Combobox.Options>{options}</Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}

export function getAvailableInputs(
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>,
  teamsMap: any,
  stageItemMap: any
) {
  const getComboBoxOptionForStageItemInput = (option: StageItemInputOption) => {
    if ('winner_from_stage_item_id' in option) {
      option.winner_position = assert_not_none(option.winner_position);
      const stageItem = stageItemMap[option.winner_from_stage_item_id];

      if (stageItem == null) return null;
      return {
        value: `${option.winner_from_stage_item_id}_${option.winner_position}`,
        label: `${formatStageItemInputTentative(option, stageItemMap)}`,
        team_id: null,
        winner_from_stage_item_id: option.winner_from_stage_item_id,
        winner_position: option.winner_position,
        already_taken: option.already_taken,
        team_level_id: null,
      };
    }

    const team = teamsMap[option.team_id];
    if (team == null) return null;
    return {
      value: `${assert_not_none(option.team_id)}`,
      label: team.name,
      team_id: team.id,
      winner_from_stage_item_id: null,
      winner_position: null,
      already_taken: option.already_taken,
      team_level_id: team.level_id,
    };
  };
  return swrAvailableInputsResponse.data != undefined
    ? Object.keys(swrAvailableInputsResponse.data?.data).reduce((result: any, stage_id: string) => {
        const option = assert_not_none(swrAvailableInputsResponse.data?.data[stage_id]);
        result[stage_id] = option
          .map((opt: StageItemInputOption) => getComboBoxOptionForStageItemInput(opt))
          .filter((o: StageItemInputOption | null) => o != null);
        return result;
      }, {})
    : {};
}

function StageItemInputSection({
  tournament,
  stageItemInput,
  currentOptionValue,
  lastInList,
  availableInputs,
  swrAvailableInputsResponse,
  swrStagesResponse,
}: {
  tournament: TournamentWithLevels;
  stageItemInput: StageItemInput;
  currentOptionValue: string | null;
  lastInList: boolean;
  availableInputs: StageItemInputChoice[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
}) {
  const opts = lastInList ? { pt: 'xs', mb: '-0.5rem' } : { py: 'xs', withBorder: true };

  return (
    <Card.Section inheritPadding {...opts}>
      <StageItemInputComboBox
        tournament={tournament}
        stageItemInput={stageItemInput}
        current_key={currentOptionValue}
        availableInputs={availableInputs}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        swrStagesResponse={swrStagesResponse}
      />
    </Card.Section>
  );
}

function StageItemRow({
  tournament,
  stageItem,
  swrStagesResponse,
  availableInputs,
  rankings,
  swrAvailableInputsResponse,
  levelId,
}: {
  tournament: TournamentWithLevels;
  stageItem: StageItemWithRounds;
  levelId: number | null;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  availableInputs: StageItemInputChoice[];
  rankings: Ranking[];
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const [confirmDeleteOpened, setConfirmDeleteOpened] = useState(false);

  const inputs = stageItem.inputs
    .sort((i1, i2) => (i1.slot > i2.slot ? 1 : -1))
    .map((input, i) => {
      let currentOptionValue = null;
      if (input.winner_from_stage_item_id != null) {
        currentOptionValue = `${input.winner_from_stage_item_id}_${input.winner_position}`;
      } else if (input.team_id != null) {
        currentOptionValue = `${input.team_id}`;
      }

      return (
        <StageItemInputSection
          key={input.id}
          tournament={tournament}
          stageItemInput={input}
          currentOptionValue={currentOptionValue}
          availableInputs={availableInputs}
          lastInList={i === stageItem.inputs.length - 1}
          swrAvailableInputsResponse={swrAvailableInputsResponse}
          swrStagesResponse={swrStagesResponse}
        />
      );
    });

  return (
    <Card withBorder shadow="sm" radius="md">
      <Card.Section withBorder inheritPadding py="xs" color="dimmed">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={800}>{stageItem.name}</Text>
            <LevelBadge levels={tournament.levels} levelId={levelId} />
          </Group>
          <UpdateStageItemModal
            swrStagesResponse={swrStagesResponse}
            stageItem={stageItem}
            tournament={tournament}
            opened={opened}
            setOpened={setOpened}
            rankings={rankings}
          />
          <ConfirmModal
            opened={confirmDeleteOpened}
            setOpened={setConfirmDeleteOpened}
            title={t('delete_stage_item_confirm_title')}
            message={t('delete_stage_item_confirm_message')}
            confirmLabel={t('delete_button')}
            onConfirm={async () => {
              await deleteStageItem(tournament.id, stageItem.id);
              await swrStagesResponse.mutate();
              await swrAvailableInputsResponse.mutate();
            }}
          />
          <Group gap="0rem">
            {stageItem.type === 'SWISS' || stageItem.type === 'MEXICANO' ? (
              <Tooltip label={t('handle_swiss_system')}>
                <ActionIcon
                  variant="transparent"
                  color="gray"
                  component={PreloadLink}
                  href={`/tournaments/${tournament.id}/stages/swiss/${stageItem.id}`}
                >
                  <BiSolidWrench size="1.25rem" />
                </ActionIcon>
              </Tooltip>
            ) : null}
            <Menu withinPortal position="bottom-end" shadow="sm">
              <Menu.Target>
                <ActionIcon variant="transparent" color="gray">
                  <IconDots size="1.25rem" />
                </ActionIcon>
              </Menu.Target>

              <Menu.Dropdown>
                <Menu.Item
                  leftSection={<IconPencil size="1.5rem" />}
                  onClick={() => {
                    setOpened(true);
                  }}
                >
                  {t('edit_stage_item_label')}
                </Menu.Item>
                {stageItem.type === 'SWISS' || stageItem.type === 'MEXICANO' ? (
                  <Menu.Item
                    leftSection={<BiSolidWrench size="1.5rem" />}
                    component={PreloadLink}
                    href={`/tournaments/${tournament.id}/stages/swiss/${stageItem.id}`}
                  >
                    {t('handle_swiss_system')}
                  </Menu.Item>
                ) : null}
                <Menu.Item
                  leftSection={<IconTrash size="1.5rem" />}
                  onClick={() => setConfirmDeleteOpened(true)}
                  color="red"
                >
                  {t('delete_button')}
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </Card.Section>
      {inputs}
    </Card>
  );
}

function StageColumn({
  tournament,
  stage,
  swrStagesResponse,
  swrAvailableInputsResponse,
  rankings,
}: {
  tournament: TournamentWithLevels;
  stage: StageWithStageItems;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  rankings: Ranking[];
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const [confirmDeleteOpened, setConfirmDeleteOpened] = useState(false);
  const [rankingModalOpened, setRankingModalOpened] = useState(false);
  const teamsMap = getTeamsLookup(tournament != null ? tournament.id : -1);
  const stageItemsLookup = getStageItemLookup(swrStagesResponse);

  if (teamsMap == null) {
    return null;
  }

  const availableInputs =
    getAvailableInputs(swrAvailableInputsResponse, teamsMap, stageItemsLookup)[stage.id] || [];
  availableInputs.push({
    value: 'null',
    label: null,
    team_id: null,
    winner_from_stage_item_id: null,
    winner_position: null,
    already_taken: false,
    team_level_id: null,
  });

  async function autoAssignTeams() {
    const emptyInputs: { stageItemId: number; inputId: number }[] = [];
    for (const stageItem of stage.stage_items) {
      for (const input of stageItem.inputs) {
        if (input.team_id == null && input.winner_from_stage_item_id == null) {
          emptyInputs.push({ stageItemId: stageItem.id, inputId: input.id });
        }
      }
    }

    const candidates = availableInputs.filter(
      (opt: StageItemInputChoice) =>
        opt.team_id != null &&
        !opt.already_taken &&
        (stage.level_id == null || opt.team_level_id === stage.level_id)
    );
    const shuffled = [...candidates].sort(() => Math.random() - 0.5);

    await Promise.all(
      emptyInputs
        .slice(0, shuffled.length)
        .map(({ stageItemId, inputId }, i) =>
          updateStageItemInput(tournament.id, stageItemId, inputId, shuffled[i].team_id, null, null)
        )
    );

    await swrStagesResponse.mutate();
    await swrAvailableInputsResponse.mutate();
  }

  const rows = stage.stage_items
    .sort((i1: StageItemWithRounds, i2: StageItemWithRounds) => (i1.id > i2.id ? 1 : -1))
    .sort((i1: StageItemWithRounds, i2: StageItemWithRounds) => (i1.name > i2.name ? 1 : -1))
    .map((stageItem: StageItemWithRounds) => (
      <StageItemRow
        key={stageItem.id}
        tournament={tournament}
        stageItem={stageItem}
        swrStagesResponse={swrStagesResponse}
        availableInputs={availableInputs}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        rankings={rankings}
        levelId={stage.level_id}
      />
    ));

  return (
    <Stack miw="24rem" align="top" key={stage.id}>
      <UpdateStageModal
        swrStagesResponse={swrStagesResponse}
        stage={stage}
        tournament={tournament}
        opened={opened}
        setOpened={setOpened}
      />
      <SetStageRankingModal
        swrStagesResponse={swrStagesResponse}
        stage={stage}
        tournament={tournament}
        rankings={rankings}
        opened={rankingModalOpened}
        setOpened={setRankingModalOpened}
      />
      <ConfirmModal
        opened={confirmDeleteOpened}
        setOpened={setConfirmDeleteOpened}
        title={t('delete_stage_confirm_title')}
        message={
          stage.stage_items.length > 0
            ? t('delete_stage_confirm_message_with_items')
            : t('delete_stage_confirm_message')
        }
        confirmLabel={t('delete_button')}
        onConfirm={async () => {
          await deleteStage(tournament.id, stage.id);
          await swrStagesResponse.mutate();
          await swrAvailableInputsResponse.mutate();
        }}
      />
      <Group justify="space-between">
        <Group>
          {stage.name}
          <LevelBadge levels={tournament.levels} levelId={stage.level_id} />
        </Group>
        <Menu withinPortal position="bottom-end" shadow="sm">
          <Menu.Target>
            <ActionIcon variant="transparent" color="gray">
              <IconDots size="1.25rem" />
            </ActionIcon>
          </Menu.Target>

          <Menu.Dropdown>
            <Menu.Item
              leftSection={<IconPencil size="1.5rem" />}
              onClick={() => {
                setOpened(true);
              }}
            >
              {t('edit_stage_label')}
            </Menu.Item>
            <Menu.Item leftSection={<IconArrowsShuffle size="1.5rem" />} onClick={autoAssignTeams}>
              {t('auto_assign_teams_label')}
            </Menu.Item>
            <Menu.Item
              leftSection={<IconListNumbers size="1.5rem" />}
              onClick={() => setRankingModalOpened(true)}
            >
              {t('set_ranking_for_stage_items_label')}
            </Menu.Item>
            <Menu.Item
              leftSection={<IconTrash size="1.5rem" />}
              onClick={() => setConfirmDeleteOpened(true)}
              color="red"
            >
              {t('delete_button')}
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      {rows}
      <CreateStageItemModal
        key={-1}
        tournament={tournament}
        stage={stage}
        rankings={rankings}
        swrStagesResponse={swrStagesResponse}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
      />
    </Stack>
  );
}

export default function Builder({
  tournament,
  registeredTeamCount,
  swrStagesResponse,
  swrAvailableInputsResponse,
  rankings,
  stages: filteredStages,
}: {
  tournament: TournamentWithLevels;
  registeredTeamCount: number;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  rankings: Ranking[];
  stages?: StageWithStageItems[];
}) {
  const { t } = useTranslation();
  const teamsMap = getTeamsLookup(tournament != null ? tournament.id : -1);
  const stages: StageWithStageItems[] =
    filteredStages ?? (swrStagesResponse.data != null ? swrStagesResponse.data.data : []);

  if (swrStagesResponse.error) return <RequestErrorAlert error={swrStagesResponse.error} />;
  if (swrAvailableInputsResponse.error) {
    return <RequestErrorAlert error={swrAvailableInputsResponse.error} />;
  }

  const sortedStages = stages.sort((s1: StageWithStageItems, s2: StageWithStageItems) =>
    s1.id > s2.id ? 1 : -1
  );

  const stageColumns = (sectionStages: StageWithStageItems[]) =>
    sectionStages.map((stage) => (
      <StageColumn
        key={stage.id}
        tournament={tournament}
        swrStagesResponse={swrStagesResponse}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        stage={stage}
        rankings={rankings}
      />
    ));

  const button = (
    <Stack miw="24rem" align="top" key={-1}>
      <h4 style={{ marginTop: '0rem' }}>
        <Group gap="xs" align="flex-start" wrap="wrap">
          <CreateStageButton
            tournament={tournament}
            swrStagesResponse={swrStagesResponse}
            swrAvailableInputsResponse={swrAvailableInputsResponse}
          />
          <CreateFromTemplateButton
            tournament={tournament}
            registeredTeamCount={registeredTeamCount}
            swrStagesResponse={swrStagesResponse}
            swrAvailableInputsResponse={swrAvailableInputsResponse}
          />
        </Group>
      </h4>
    </Stack>
  );

  if (tournament.levels.length === 0) {
    return (
      <Group align="top">
        {stageColumns(sortedStages)}
        {button}
      </Group>
    );
  }

  const assignedTeamIds = new Set(
    swrStagesResponse.data != null ? getAssignedTeamIds(swrStagesResponse) : []
  );
  const teams: FullTeamWithPlayers[] = teamsMap != null ? Object.values(teamsMap) : [];
  const unassignedTeamCountForLevel = (levelId: number | null) =>
    teams.filter((team) => (team.level_id ?? null) === levelId && !assignedTeamIds.has(team.id))
      .length;

  const sections: { level: LevelResponse | null; stages: StageWithStageItems[] }[] = [];
  const levelsByPosition = [...tournament.levels].sort((l1, l2) => l1.position - l2.position);
  for (const level of levelsByPosition) {
    const levelStages = sortedStages.filter((stage) => stage.level_id === level.id);
    if (levelStages.length > 0) {
      sections.push({ level, stages: levelStages });
    }
  }
  const noLevelStages = sortedStages.filter((stage) => stage.level_id == null);
  if (noLevelStages.length > 0) {
    sections.push({ level: null, stages: noLevelStages });
  }

  return (
    <Stack gap="md">
      {sections.map((section, index) => (
        <Stack key={section.level != null ? section.level.id : 'no-level'} gap="xs">
          {index > 0 ? <Divider /> : null}
          <Group gap="xs">
            {section.level != null ? (
              <LevelBadge levels={tournament.levels} levelId={section.level.id} />
            ) : (
              <Badge color="gray" variant="light">
                {t('no_level_section_label')}
              </Badge>
            )}
            <Text c="dimmed" size="sm">
              {section.level != null
                ? t('level_unassigned_teams_notice', {
                    count: unassignedTeamCountForLevel(section.level.id),
                  })
                : t('no_level_unassigned_teams_notice', {
                    count: unassignedTeamCountForLevel(null),
                  })}
            </Text>
          </Group>
          <Group align="top">{stageColumns(section.stages)}</Group>
        </Stack>
      ))}
      {sections.length > 0 ? <Divider /> : null}
      <Group align="top">{button}</Group>
    </Stack>
  );
}
