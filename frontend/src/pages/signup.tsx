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
import type { SignupBody, SignupInfoResponse } from '@openapi';
import { getSignupInfo, submitSignup } from '@services/signup';

type PageState = 'loading' | 'load_error' | 'form' | 'success';

function detailFromAxiosError(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data != null) {
    const data = err.response.data as { detail?: unknown };
    if (typeof data.detail === 'string') return data.detail;
  }
  return '';
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

  const maxTeamSize = info.data.max_team_size;
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
            const body: SignupBody = {
              player_name: values.player_name.trim(),
              team_action: values.team_action,
              team_id:
                values.team_action === 'join' && values.team_id != null
                  ? parseInt(values.team_id, 10)
                  : null,
              team_name:
                values.team_action === 'create' ? values.team_name.trim() : null,
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
            <Text size="sm">{t('signup_description')}</Text>

            <TextInput
              withAsterisk
              label={t('signup_player_name_label')}
              placeholder={t('signup_player_name_placeholder')}
              maxLength={30}
              {...form.getInputProps('player_name')}
            />

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
                data={joinableTeams.map((team) => ({
                  value: `${team.id}`,
                  label: `${team.name} (${team.player_count}/${maxTeamSize})`,
                }))}
                {...form.getInputProps('team_id')}
              />
            ) : null}

            {form.values.team_action === 'create' ? (
              <TextInput
                withAsterisk
                label={t('signup_team_name_label')}
                placeholder={t('signup_team_name_placeholder')}
                maxLength={30}
                {...form.getInputProps('team_name')}
              />
            ) : null}

            <Button type="submit">{t('signup_submit_button')}</Button>
          </Stack>
        </form>
      )}
    </Container>
  );
}
