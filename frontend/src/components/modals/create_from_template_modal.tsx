import { Button, Modal, NumberInput, SegmentedControl, Stack, Text } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { IconLayoutGrid } from '@tabler/icons-react';
import { AxiosError } from 'axios';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import {
  StageItemInputOptionsResponse,
  StageRankingResponse,
  StagesWithStageItemsResponse,
  Tournament,
} from '@openapi';
import { handleRequestError } from '@services/adapter';
import { createStagesFromTemplate } from '@services/stage';

function normalizeTotalTeams(raw: number, groups: 2 | 4): number {
  let n = Math.max(4, raw);
  while (n % groups !== 0) {
    n += 1;
  }
  return n;
}

export function CreateFromTemplateButton({
  tournament,
  registeredTeamCount,
  swrStagesResponse,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
  buttonSize = 'xs',
}: {
  tournament: Tournament;
  registeredTeamCount: number;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
  buttonSize?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}) {
  const { t } = useTranslation();
  const [opened, { open, close }] = useDisclosure(false);

  return (
    <>
      <Button
        variant="outline"
        color="blue"
        size={buttonSize}
        onClick={open}
        leftSection={<IconLayoutGrid size={buttonSize === 'lg' ? 24 : 18} />}
      >
        {t('create_from_template_button')}
      </Button>
      <CreateFromTemplateModal
        tournament={tournament}
        opened={opened}
        onClose={close}
        registeredTeamCount={registeredTeamCount}
        swrStagesResponse={swrStagesResponse}
        swrAvailableInputsResponse={swrAvailableInputsResponse}
        swrRankingsPerStageItemResponse={swrRankingsPerStageItemResponse}
      />
    </>
  );
}

function CreateFromTemplateModal({
  tournament,
  opened,
  onClose,
  registeredTeamCount,
  swrStagesResponse,
  swrAvailableInputsResponse,
  swrRankingsPerStageItemResponse,
}: {
  tournament: Tournament;
  opened: boolean;
  onClose: () => void;
  registeredTeamCount: number;
  swrStagesResponse: SWRResponse<StagesWithStageItemsResponse>;
  swrAvailableInputsResponse: SWRResponse<StageItemInputOptionsResponse>;
  swrRankingsPerStageItemResponse: SWRResponse<StageRankingResponse>;
}) {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const hasResetForOpen = useRef(false);

  const form = useForm({
    initialValues: {
      groups: 2 as 2 | 4,
      total_teams: normalizeTotalTeams(registeredTeamCount, 2),
    },
    validate: {
      total_teams: (value, values) => {
        if (value < 4) {
          return t('template_total_teams_min_error');
        }
        return null;
      },
    },
  });

  useEffect(() => {
    if (!opened) {
      hasResetForOpen.current = false;
      return;
    }
    if (!hasResetForOpen.current) {
      const groups: 2 | 4 = 2;
      form.setValues({
        groups,
        total_teams: normalizeTotalTeams(registeredTeamCount, groups),
      });
      hasResetForOpen.current = true;
    }
    // form.setValues is stable; listing `form` can trigger redundant effect runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, registeredTeamCount]);

  return (
    <Modal opened={opened} onClose={onClose} title={t('create_from_template_modal_title')}>
      <form
        onSubmit={form.onSubmit(async (values) => {
          setSubmitting(true);
          try {
            await createStagesFromTemplate(tournament.id, {
              groups: values.groups,
              total_teams: values.total_teams,
              until_rank: 'all',
              include_semi_final: true,
            });
            await swrStagesResponse.mutate();
            await swrAvailableInputsResponse.mutate();
            await swrRankingsPerStageItemResponse.mutate();
            onClose();
          } catch (exc: unknown) {
            if (exc instanceof AxiosError) {
              handleRequestError(exc);
              return;
            }
            throw exc;
          } finally {
            setSubmitting(false);
          }
        })}
      >
        <Stack gap="md" mt="xs">
          <div>
            <Text size="sm" fw={500} mb={6}>
              {t('template_wizard_groups_label')}
            </Text>
            <SegmentedControl
              fullWidth
              data={[
                { label: '2', value: '2' },
                { label: '4', value: '4' },
              ]}
              value={String(form.values.groups)}
              onChange={(v) => {
                const groups = Number(v) as 2 | 4;
                form.setFieldValue('groups', groups);
                form.setFieldValue(
                  'total_teams',
                  normalizeTotalTeams(form.values.total_teams, groups),
                );
              }}
            />
          </div>

          <NumberInput
            label={t('template_wizard_total_teams_label')}
            min={4}
            {...form.getInputProps('total_teams')}
          />

          <Text size="sm" c="dimmed">
            {t('template_wizard_rank_all_description')}
          </Text>

          <Button type="submit" color="green" fullWidth loading={submitting}>
            {t('create_from_template_submit_button')}
          </Button>
        </Stack>
      </form>
    </Modal>
  );
}
