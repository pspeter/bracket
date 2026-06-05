import {
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  MultiSelect,
  Select,
  Tabs,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconUser, IconUsers, IconUsersPlus } from '@tabler/icons-react';
import { AxiosError } from 'axios';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { mutate, SWRResponse } from 'swr';

import SaveButton from '@components/buttons/save';
import { MultiTeamsInput } from '@components/forms/player_create_csv_input';
import { LevelResponse, Player, TeamsWithPlayersResponse } from '@openapi';
import {
  getPlayers,
  getPlayersKey,
  getTournamentById,
  handleRequestError,
} from '@services/adapter';
import { stringToColour } from '@services/lookups';
import { createTeam, createTeams } from '@services/team';

type PlayerOption = {
  value: string;
  label: string;
  level_id: number | null;
  level_name: string | null;
};

function playerSelectData(players: Player[], levelNameById: Map<number, string>): PlayerOption[] {
  return players.map((p) => ({
    value: `${p.id}`,
    label: p.name,
    level_id: p.level_id,
    level_name: p.level_id != null ? (levelNameById.get(p.level_id) ?? null) : null,
  }));
}

function PlayerSelectOption({ option }: { option: PlayerOption }) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Text size="sm">{option.label}</Text>
      {option.level_id != null && (
        <Badge size="xs" color={stringToColour(`level-${option.level_id}`)} variant="light">
          {option.level_name ?? `Level ${option.level_id}`}
        </Badge>
      )}
    </Group>
  );
}

function levelSelectData(levels: LevelResponse[]) {
  return levels.map((l) => ({ value: `${l.id}`, label: l.name }));
}

function MultiTeamTab({
  tournament_id,
  levels,
  swrTeamsResponse,
  setOpened,
}: {
  tournament_id: number;
  levels: LevelResponse[];
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
  setOpened: any;
}) {
  const { t } = useTranslation();
  const form = useForm({
    initialValues: {
      names: '',
      active: true,
      level_id: '' as string,
    },

    validate: {
      names: (value) => (value.length > 0 ? null : t('at_least_one_team_validation')),
      level_id: (value) => (levels.length > 0 && !value ? t('too_short_name_validation') : null),
    },
  });
  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        try {
          const levelId = values.level_id ? Number(values.level_id) : null;
          await createTeams(tournament_id, values.names, values.active, levelId);
          await swrTeamsResponse.mutate();
          setOpened(false);
        } catch (exc: unknown) {
          if (exc instanceof AxiosError) {
            handleRequestError(exc);
            return;
          }
          throw exc;
        }
      })}
    >
      <MultiTeamsInput form={form} />

      {levels.length > 0 && (
        <Select
          withAsterisk
          mt="md"
          label="Level"
          placeholder="Select level"
          data={levelSelectData(levels)}
          {...form.getInputProps('level_id')}
        />
      )}

      <Checkbox
        mt="md"
        label={t('active_teams_checkbox_label')}
        {...form.getInputProps('active', { type: 'checkbox' })}
      />
      <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
        {t('save_button')}
      </Button>
    </form>
  );
}

function SingleTeamTab({
  tournament_id,
  levels,
  swrTeamsResponse,
  setOpened,
}: {
  tournament_id: number;
  levels: LevelResponse[];
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
  setOpened: any;
}) {
  const { t } = useTranslation();
  const swrTournament = getTournamentById(tournament_id);
  const allowPlayersInMultipleTeams =
    swrTournament.data?.data.players_can_be_in_multiple_teams ?? false;
  const { data } = getPlayers(tournament_id, !allowPlayersInMultipleTeams);
  const players: Player[] = data != null ? data.data.players : [];
  const levelNameById = new Map(levels.map((l) => [l.id, l.name]));
  const playerOptions = playerSelectData(players, levelNameById);
  const maxTeamSize = swrTournament.data?.data.max_team_size;
  const form = useForm({
    initialValues: {
      name: '',
      active: true,
      player_ids: [],
      level_id: '' as string,
    },
    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
      level_id: (value) => (levels.length > 0 && !value ? t('too_short_name_validation') : null),
    },
  });
  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        try {
          const levelId = values.level_id ? Number(values.level_id) : null;
          await createTeam(tournament_id, values.name, values.active, values.player_ids, levelId);
          await swrTeamsResponse.mutate();
          await mutate(getPlayersKey(tournament_id, true));
          setOpened(false);
        } catch (exc: unknown) {
          if (exc instanceof AxiosError) {
            handleRequestError(exc);
            return;
          }
          throw exc;
        }
      })}
    >
      <TextInput
        withAsterisk
        label={t('name_input_label')}
        placeholder={t('team_name_input_placeholder')}
        {...form.getInputProps('name')}
      />

      {levels.length > 0 && (
        <Select
          withAsterisk
          mt="md"
          label="Level"
          placeholder="Select level"
          data={levelSelectData(levels)}
          {...form.getInputProps('level_id')}
        />
      )}

      <Checkbox
        mt="md"
        label={t('active_teams_checkbox_label')}
        {...form.getInputProps('active', { type: 'checkbox' })}
      />

      <MultiSelect
        data={playerOptions}
        renderOption={({ option }) => <PlayerSelectOption option={option as PlayerOption} />}
        label={t('team_member_select_title')}
        placeholder={t('team_member_select_placeholder')}
        maxDropdownHeight={160}
        searchable
        mb="12rem"
        mt={12}
        limit={25}
        maxValues={maxTeamSize}
        {...form.getInputProps('player_ids')}
      />
      <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
        {t('save_button')}
      </Button>
    </form>
  );
}

export default function TeamCreateModal({
  tournament_id,
  swrTeamsResponse,
}: {
  tournament_id: number;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
}) {
  const { t } = useTranslation();
  const [opened, setOpened] = useState(false);
  const swrTournament = getTournamentById(tournament_id);
  const levels = swrTournament.data?.data.levels ?? [];
  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Create Team">
        <Tabs defaultValue="single">
          <Tabs.List justify="center" grow>
            <Tabs.Tab value="single" leftSection={<IconUser size="0.8rem" />}>
              {t('single_team')}
            </Tabs.Tab>
            <Tabs.Tab value="multi" leftSection={<IconUsers size="0.8rem" />}>
              {t('multiple_teams')}
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="single" pt="xs">
            <SingleTeamTab
              swrTeamsResponse={swrTeamsResponse}
              tournament_id={tournament_id}
              levels={levels}
              setOpened={setOpened}
            />
          </Tabs.Panel>

          <Tabs.Panel value="multi" pt="xs">
            <MultiTeamTab
              swrTeamsResponse={swrTeamsResponse}
              tournament_id={tournament_id}
              levels={levels}
              setOpened={setOpened}
            />
          </Tabs.Panel>
        </Tabs>
      </Modal>

      <SaveButton
        onClick={() => setOpened(true)}
        leftSection={<IconUsersPlus size={24} />}
        title={t('add_team_button')}
        mb={0}
      />
    </>
  );
}
