import {
  Badge,
  Button,
  Center,
  Checkbox,
  Fieldset,
  Group,
  Image,
  Modal,
  MultiSelect,
  Select,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { BiEditAlt } from '@react-icons/all-files/bi/BiEditAlt';
import { AxiosError } from 'axios';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { mutate, SWRResponse } from 'swr';

import { DropzoneButton } from '@components/utils/file_upload';
import { levelColour } from '@logic/colors';
import { FullTeamWithPlayers, LevelResponse, Player, TeamsWithPlayersResponse } from '@openapi';
import {
  getBaseApiUrl,
  getPlayers,
  getPlayersKey,
  getTournamentById,
  handleRequestError,
  removeTeamLogo,
} from '@services/adapter';
import { updateTeam } from '@services/team';

function playerSelectData(players: Player[], levelNameById: Map<number, string>) {
  return players.map((p) => ({
    value: `${p.id}`,
    label: p.name,
    level_id: p.level_id,
    level_name: p.level_id != null ? (levelNameById.get(p.level_id) ?? null) : null,
  }));
}

type PlayerOption = ReturnType<typeof playerSelectData>[number];

function PlayerSelectOption({ option, levels }: { option: PlayerOption; levels: LevelResponse[] }) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Text size="sm">{option.label}</Text>
      {option.level_id != null && (
        <Badge size="xs" color={levelColour(option.level_id, levels)} variant="light">
          {option.level_name ?? `Level ${option.level_id}`}
        </Badge>
      )}
    </Group>
  );
}

function TeamLogo({ team }: { team: FullTeamWithPlayers | null }) {
  if (team == null || team.logo_path == null) return null;
  return (
    <Image
      radius="md"
      alt="Logo of the team"
      src={`${getBaseApiUrl()}/static/team-logos/${team.logo_path}`}
    />
  );
}

export default function TeamUpdateModal({
  tournament_id,
  team,
  swrTeamsResponse,
}: {
  tournament_id: number;
  team: FullTeamWithPlayers;
  swrTeamsResponse: SWRResponse<TeamsWithPlayersResponse>;
}) {
  const { t } = useTranslation();
  const swrTournament = getTournamentById(tournament_id);
  const allowPlayersInMultipleTeams =
    swrTournament.data?.data.players_can_be_in_multiple_teams ?? false;
  const { data } = getPlayers(tournament_id, !allowPlayersInMultipleTeams);
  const playersFromApi: Player[] = data != null ? data.data.players : [];
  const playersById = new Map<string, Player>();
  for (const player of [...team.players, ...playersFromApi]) {
    playersById.set(`${player.id}`, player);
  }
  const players = [...playersById.values()];
  const maxTeamSize = swrTournament.data?.data.max_team_size;
  const levels: LevelResponse[] = swrTournament.data?.data.levels ?? [];
  const levelNameById = new Map(levels.map((l) => [l.id, l.name]));
  const playerOptions = playerSelectData(players, levelNameById);
  const [opened, setOpened] = useState(false);

  const form = useForm({
    initialValues: {
      name: team.name,
      active: team.active,
      player_ids: team.players.map((player) => `${player.id}`),
      level_id: team.level_id != null ? `${team.level_id}` : '',
    },

    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
      level_id: (value) => (levels.length > 0 && !value ? t('too_short_name_validation') : null),
    },
  });

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={t('edit_team_title')}>
        <form
          onSubmit={form.onSubmit(async (values) => {
            try {
              const levelId = values.level_id ? Number(values.level_id) : null;
              await updateTeam(
                tournament_id,
                team.id,
                values.name,
                values.active,
                values.player_ids,
                levelId
              );
              await swrTeamsResponse.mutate();
              await mutate(getPlayersKey(tournament_id, true));
              setOpened(false);
            } catch (exc: unknown) {
              if (
                exc instanceof AxiosError &&
                exc.response?.data != null &&
                typeof exc.response.data === 'object' &&
                'detail' in exc.response.data &&
                exc.response.data.detail === 'This team is full'
              ) {
                showNotification({
                  color: 'red',
                  title: t('signup_team_full'),
                  message: '',
                  autoClose: 8000,
                });
                return;
              }
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
              data={levels.map((l) => ({ value: `${l.id}`, label: l.name }))}
              {...form.getInputProps('level_id')}
            />
          )}

          <Checkbox
            mt="md"
            label={t('active_team_checkbox_label')}
            {...form.getInputProps('active', { type: 'checkbox' })}
          />

          <MultiSelect
            data={playerOptions}
            renderOption={({ option }) => (
              <PlayerSelectOption option={option as PlayerOption} levels={levels} />
            )}
            label={t('team_member_select_title')}
            placeholder={t('team_member_select_placeholder')}
            maxDropdownHeight={160}
            searchable
            mt={12}
            limit={25}
            maxValues={maxTeamSize}
            {...form.getInputProps('player_ids')}
          />

          <Fieldset legend={t('logo_settings_title')} mt={12} radius="md">
            <DropzoneButton
              tournamentId={tournament_id}
              teamId={team.id}
              swrResponse={swrTeamsResponse}
              variant="team"
            />
            <Center my="lg">
              <div style={{ width: '50%' }}>
                <TeamLogo team={team} />
              </div>
            </Center>
            <Button
              variant="outline"
              color="red"
              fullWidth
              onClick={async () => {
                await removeTeamLogo(tournament_id, team.id);
                await swrTeamsResponse.mutate();
              }}
            >
              {t('remove_logo')}
            </Button>
          </Fieldset>

          <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
            {t('save_button')}
          </Button>
        </form>
      </Modal>

      <Button
        color="green"
        size="xs"
        style={{ marginRight: 10 }}
        onClick={() => setOpened(true)}
        leftSection={<BiEditAlt size={20} />}
      >
        {t('edit_team_title')}
      </Button>
    </>
  );
}
