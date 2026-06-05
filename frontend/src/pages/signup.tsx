import {
  Alert,
  Button,
  Container,
  Loader,
  Radio,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { showNotification } from '@mantine/notifications';
import { AxiosError } from 'axios';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router';

import { getBaseURL } from '@components/utils/util';
import type { LevelResponse, SignupBody, SignupInfoResponse, SignupTeamInfo } from '@openapi';
import { getSignupInfo, submitSignup } from '@services/signup';

type PageState = 'loading' | 'load_error' | 'form' | 'success';

function detailFromAxiosError(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data != null) {
    const data = err.response.data as { detail?: unknown };
    if (typeof data.detail === 'string') return data.detail;
  }
  return '';
}

function levelSelectData(levels: LevelResponse[]) {
  return levels.map((level) => ({ value: `${level.id}`, label: level.name }));
}

function teamSelectData(teams: SignupTeamInfo[], levels: LevelResponse[], maxTeamSize: number) {
  const levelNameById = new Map(levels.map((level) => [level.id, level.name]));
  if (levels.length === 0) {
    return teams.map((team) => ({
      value: `${team.id}`,
      label: `${team.name} (${team.player_count}/${maxTeamSize})`,
    }));
  }

  return levels.map((level) => ({
    group: level.name,
    items: teams
      .filter((team) => team.level_id === level.id)
      .map((team) => ({
        value: `${team.id}`,
        label: `${team.name} · ${levelNameById.get(level.id)} (${team.player_count}/${maxTeamSize})`,
      })),
  }));
}

export default function SignupPage() {
  const { signup_token } = useParams<{ signup_token: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [pageState, setPageState] = useState<PageState>('loading');
  const [info, setInfo] = useState<SignupInfoResponse | null>(null);

  const form = useForm({
    initialValues: {
      player_name: '',
      team_action: 'none' as SignupBody['team_action'],
      team_id: null as string | null,
      team_name: '',
      level_id: null as string | null,
    },
    validate: {
      player_name: (v) =>
        v.trim().length > 0 && v.length <= 30 ? null : t('too_short_name_validation'),
      team_name: (v, values) => {
        if (values.team_action !== 'create') return null;
        const s = v.trim();
        return s.length > 0 && s.length <= 30 ? null : t('too_short_name_validation');
      },
      team_id: (_v, values) => {
        if (values.team_action !== 'join') return null;
        return values.team_id != null && values.team_id !== '' ? null : t('club_choose_title');
      },
      level_id: (_v, values) => {
        const teamChoiceEnabled = info?.data.signup_team_choice_enabled ?? true;
        const effectivelyTeamless = !teamChoiceEnabled || values.team_action === 'none';
        const needsLevel = values.team_action === 'create' || effectivelyTeamless;
        if (!needsLevel) return null;
        return (info?.data.levels ?? []).length === 0 ||
          (values.level_id != null && values.level_id !== '')
          ? null
          : t('signup_level_select_placeholder');
      },
    },
  });

  useEffect(() => {
    if (signup_token == null || signup_token === '') {
      setPageState('load_error');
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await getSignupInfo(signup_token);
        if (!cancelled) {
          setInfo(res.data as SignupInfoResponse);
          setPageState('form');
        }
      } catch {
        if (!cancelled) setPageState('load_error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [signup_token]);

  useEffect(() => {
    if (pageState !== 'success' || info == null) return;

    const endpoint = info.data.dashboard_endpoint;
    if (endpoint == null || endpoint === '') return undefined;

    const tmr = window.setTimeout(() => {
      navigate(`/tournaments/${endpoint}/dashboard`);
    }, 2000);
    return () => window.clearTimeout(tmr);
  }, [pageState, info, navigate]);

  if (signup_token == null || signup_token === '') {
    return (
      <Container size="sm" py="xl">
        <Alert color="red">{t('signup_invalid_link')}</Alert>
      </Container>
    );
  }

  if (pageState === 'loading') {
    return (
      <Container size="sm" py="xl">
        <Loader />
      </Container>
    );
  }

  if (pageState === 'load_error') {
    return (
      <Container size="sm" py="xl">
        <Alert color="red">{t('signup_invalid_link')}</Alert>
      </Container>
    );
  }

  if (info == null) return null;

  const teamChoiceEnabled = info.data.signup_team_choice_enabled ?? true;
  const maxTeamSize = info.data.max_team_size;
  const levels = info.data.levels;
  const hasLevels = levels.length > 0;
  const joinableTeams = info.data.teams.filter((team) => !team.is_full);

  const notifySubmitError = (detail: string) => {
    let message = detail;
    if (detail.includes('already exists')) message = t('signup_duplicate_name');
    else if (detail === 'Tournament is full') message = t('signup_tournament_full');
    else if (detail === 'This team is full') message = t('signup_team_full');

    showNotification({ color: 'red', title: 'Error', message });
  };

  return (
    <Container size="sm" py="xl">
      {pageState === 'success' ? (
        <Stack>
          <Title order={2}>{t('signup_success_message')}</Title>
          {info.data.dashboard_endpoint != null && info.data.dashboard_endpoint !== '' ? (
            <Text size="sm" c="dimmed">
              {t('signup_redirecting')}
            </Text>
          ) : null}
          {info.data.dashboard_endpoint != null && info.data.dashboard_endpoint !== '' ? (
            <Button
              component="a"
              href={`${getBaseURL()}/tournaments/${info.data.dashboard_endpoint}/dashboard`}
            >
              {t('signup_view_dashboard')}
            </Button>
          ) : null}
        </Stack>
      ) : (
        <form
          onSubmit={form.onSubmit(async (values) => {
            const action = teamChoiceEnabled ? values.team_action : 'none';
            const body: SignupBody = {
              player_name: values.player_name.trim(),
              team_action: action,
              team_id:
                action === 'join' && values.team_id != null ? parseInt(values.team_id, 10) : null,
              team_name: action === 'create' ? values.team_name.trim() : null,
              level_id:
                (action === 'create' || action === 'none') &&
                values.level_id != null &&
                values.level_id !== ''
                  ? parseInt(values.level_id, 10)
                  : null,
            };

            try {
              await submitSignup(signup_token, body);
              setPageState('success');
            } catch (err) {
              notifySubmitError(detailFromAxiosError(err));
            }
          })}
        >
          <Stack gap="md">
            <Title order={2}>
              {t('signup_page_title', { tournamentName: info.data.tournament_name })}
            </Title>
            <Text size="sm">
              {teamChoiceEnabled ? t('signup_description') : t('signup_description_no_teams')}
            </Text>

            <TextInput
              withAsterisk
              label={t('signup_player_name_label')}
              placeholder={t('signup_player_name_placeholder')}
              maxLength={30}
              {...form.getInputProps('player_name')}
            />

            {teamChoiceEnabled ? (
              <>
                <Radio.Group
                  label={t('signup_team_action_label')}
                  {...form.getInputProps('team_action')}
                >
                  <Stack gap="xs" mt="xs">
                    <Radio value="join" label={t('signup_join_team')} />
                    <Radio value="create" label={t('signup_create_team')} />
                    <Radio value="none" label={t('signup_no_team')} />
                  </Stack>
                </Radio.Group>

                {form.values.team_action === 'join' ? (
                  <Select
                    label={t('teams_title')}
                    placeholder={t('signup_team_select_placeholder')}
                    data={teamSelectData(joinableTeams, levels, maxTeamSize)}
                    {...form.getInputProps('team_id')}
                  />
                ) : null}

                {form.values.team_action === 'create' ? (
                  <>
                    {hasLevels ? (
                      <Select
                        withAsterisk
                        label={t('signup_level_label')}
                        placeholder={t('signup_level_select_placeholder')}
                        data={levelSelectData(levels)}
                        {...form.getInputProps('level_id')}
                      />
                    ) : null}
                    <TextInput
                      withAsterisk
                      label={t('signup_team_name_label')}
                      placeholder={t('signup_team_name_placeholder')}
                      maxLength={30}
                      {...form.getInputProps('team_name')}
                    />
                  </>
                ) : null}

                {form.values.team_action === 'none' && hasLevels ? (
                  <Select
                    withAsterisk
                    label={t('signup_level_label')}
                    placeholder={t('signup_level_select_placeholder')}
                    data={levelSelectData(levels)}
                    {...form.getInputProps('level_id')}
                  />
                ) : null}
              </>
            ) : (
              <>
                {hasLevels ? (
                  <Select
                    withAsterisk
                    label={t('signup_level_label')}
                    placeholder={t('signup_level_select_placeholder')}
                    data={levelSelectData(levels)}
                    {...form.getInputProps('level_id')}
                  />
                ) : null}
              </>
            )}

            <Button type="submit">{t('signup_submit_button')}</Button>
          </Stack>
        </form>
      )}
    </Container>
  );
}
