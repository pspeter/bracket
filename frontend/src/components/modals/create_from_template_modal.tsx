import {
  Button,
  Modal,
  NumberInput,
  Paper,
  Radio,
  Select,
  Stack,
  Switch,
  Text,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDisclosure } from '@mantine/hooks';
import { IconLayoutGrid } from '@tabler/icons-react';
import { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
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
import {
  englishOrdinalSuffix,
  evenRankOptions,
  groupTeamCounts,
  knockoutMatchLabels,
  maxUntilRankForTemplate,
  resolveUntilRank,
} from '@utils/template_wizard_preview';

function normalizeTotalTeams(raw: number, groups: 2 | 4): number {
  let n = Math.max(4, raw);
  while (n % groups !== 0) {
    n += 1;
  }
  return n;
}

function defaultIncludeSemiFinal(totalTeams: number, groups: 2 | 4): boolean {
  if (groups !== 2) {
    return true;
  }
  const tpg = Math.floor(totalTeams / groups);
  return totalTeams >= 5 && tpg >= 3;
}

type TemplateFormValues = {
  groups: 2 | 4;
  total_teams: number;
  until_rank: 'all' | number;
  include_semi_final: boolean;
};

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
  const [replaceConfirmOpen, setReplaceConfirmOpen] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState<TemplateFormValues | null>(null);

  const existingStages = swrStagesResponse.data?.data ?? [];
  const hasExistingStages = existingStages.length > 0;

  const form = useForm<TemplateFormValues>({
    initialValues: {
      groups: 2,
      total_teams: normalizeTotalTeams(registeredTeamCount, 2),
      until_rank: 'all',
      include_semi_final: defaultIncludeSemiFinal(normalizeTotalTeams(registeredTeamCount, 2), 2),
    },
    validate: {
      total_teams: (value) => {
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
      const total = normalizeTotalTeams(registeredTeamCount, groups);
      form.setValues({
        groups,
        total_teams: total,
        until_rank: 'all',
        include_semi_final: defaultIncludeSemiFinal(total, groups),
      });
      hasResetForOpen.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, registeredTeamCount]);

  const maxRank = maxUntilRankForTemplate(form.values.groups, form.values.total_teams);

  const showSemiToggle =
    form.values.groups === 2 &&
    form.values.total_teams >= 5 &&
    Math.floor(form.values.total_teams / 2) >= 3;

  const effectiveIncludeSemiFinal =
    form.values.groups === 4 ? true : showSemiToggle ? form.values.include_semi_final : false;

  useEffect(() => {
    if (!opened) {
      return;
    }
    const tpg = Math.floor(form.values.total_teams / form.values.groups);
    if (form.values.groups === 2 && tpg < 3 && form.values.include_semi_final) {
      form.setFieldValue('include_semi_final', false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, form.values.total_teams, form.values.groups]);

  useEffect(() => {
    if (!opened) {
      return;
    }
    const ur = form.values.until_rank;
    if (ur !== 'all' && typeof ur === 'number' && ur > maxRank) {
      form.setFieldValue('until_rank', 'all');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, maxRank, form.values.until_rank]);

  const resolvedUntil = resolveUntilRank(
    form.values.until_rank,
    form.values.groups,
    form.values.total_teams
  );

  const preview = useMemo(() => {
    const sizes = groupTeamCounts(form.values.total_teams, form.values.groups);
    const ko = knockoutMatchLabels(
      form.values.groups,
      form.values.total_teams,
      effectiveIncludeSemiFinal,
      resolvedUntil
    );
    return { sizes, ko };
  }, [form.values.groups, form.values.total_teams, effectiveIncludeSemiFinal, resolvedUntil]);

  const rankSelectData = useMemo(() => {
    const opts = [{ value: 'all', label: t('template_wizard_rank_option_all') }];
    for (const r of evenRankOptions(maxRank)) {
      opts.push({
        value: String(r),
        label: t('template_wizard_rank_option_nth', {
          rank: r,
          ordinal_suffix: englishOrdinalSuffix(r),
        }),
      });
    }
    return opts;
  }, [maxRank, t]);

  const rankSelectValue = form.values.until_rank === 'all' ? 'all' : String(form.values.until_rank);

  const teamsPerGroupDisplay = Math.floor(form.values.total_teams / form.values.groups);

  const runSubmit = async (values: TemplateFormValues) => {
    setSubmitting(true);
    try {
      const semiToggleVisible =
        values.groups === 2 && values.total_teams >= 5 && Math.floor(values.total_teams / 2) >= 3;
      const includeSemiFinal =
        values.groups === 4 ? true : semiToggleVisible ? values.include_semi_final : false;
      await createStagesFromTemplate(tournament.id, {
        groups: values.groups,
        total_teams: values.total_teams,
        until_rank: values.until_rank,
        include_semi_final: includeSemiFinal,
      });
      await swrStagesResponse.mutate();
      await swrAvailableInputsResponse.mutate();
      await swrRankingsPerStageItemResponse.mutate();
      setReplaceConfirmOpen(false);
      setPendingSubmit(null);
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
  };

  const onPrimarySubmit = form.onSubmit(async (values) => {
    const includeSemiFinal =
      values.groups === 4 ? true : showSemiToggle ? values.include_semi_final : false;
    const payload: TemplateFormValues = { ...values, include_semi_final: includeSemiFinal };
    if (hasExistingStages) {
      setPendingSubmit(payload);
      setReplaceConfirmOpen(true);
      return;
    }
    await runSubmit(payload);
  });

  return (
    <>
      <Modal opened={opened} onClose={onClose} title={t('create_from_template_modal_title')}>
        <form onSubmit={onPrimarySubmit}>
          <Stack gap="md" mt="xs">
            <Radio.Group
              label={t('template_wizard_groups_label')}
              value={String(form.values.groups)}
              onChange={(v) => {
                const groups = Number(v) as 2 | 4;
                const total = normalizeTotalTeams(form.values.total_teams, groups);
                form.setValues({
                  groups,
                  total_teams: total,
                  until_rank: 'all',
                  include_semi_final: defaultIncludeSemiFinal(total, groups),
                });
              }}
            >
              <Stack gap="sm" mt={6}>
                <Radio
                  value="2"
                  label={t('template_wizard_groups_option_2')}
                  description={t('template_wizard_groups_hint_2', {
                    tpg: Math.floor(form.values.total_teams / 2),
                    total: form.values.total_teams,
                  })}
                />
                <Radio
                  value="4"
                  label={t('template_wizard_groups_option_4')}
                  description={t('template_wizard_groups_hint_4', {
                    tpg: Math.floor(form.values.total_teams / 4),
                    total: form.values.total_teams,
                  })}
                />
              </Stack>
            </Radio.Group>

            <NumberInput
              label={t('template_wizard_total_teams_label')}
              description={t('template_wizard_total_teams_description')}
              min={4}
              {...form.getInputProps('total_teams')}
            />

            <Select
              label={t('template_wizard_rank_label')}
              data={rankSelectData}
              value={rankSelectValue}
              onChange={(v) => {
                if (v == null || v === 'all') {
                  form.setFieldValue('until_rank', 'all');
                } else {
                  form.setFieldValue('until_rank', Number(v));
                }
              }}
            />

            {showSemiToggle ? (
              <Switch
                label={t('template_wizard_include_semi_label')}
                description={t('template_wizard_include_semi_description')}
                checked={form.values.include_semi_final}
                onChange={(e) => form.setFieldValue('include_semi_final', e.currentTarget.checked)}
              />
            ) : null}

            <Paper withBorder p="sm" radius="md">
              <Text size="sm" fw={600} mb={6}>
                {t('template_wizard_summary_title')}
              </Text>
              <Text size="sm">
                {t('template_wizard_summary_body', {
                  groups: form.values.groups,
                  sizes: preview.sizes.join(' · '),
                  teamsPerGroup: teamsPerGroupDisplay,
                  knockout: preview.ko.join(', '),
                })}
              </Text>
            </Paper>

            <Button type="submit" color="green" fullWidth loading={submitting}>
              {t('create_from_template_submit_button')}
            </Button>
          </Stack>
        </form>
      </Modal>

      <Modal
        opened={replaceConfirmOpen}
        onClose={() => {
          setReplaceConfirmOpen(false);
          setPendingSubmit(null);
        }}
        title={t('template_wizard_confirm_replace_title')}
      >
        <Stack gap="md">
          <Text size="sm">{t('template_wizard_confirm_replace_message')}</Text>
          <Button
            color="red"
            fullWidth
            loading={submitting}
            onClick={async () => {
              if (pendingSubmit != null) {
                await runSubmit(pendingSubmit);
              }
            }}
          >
            {t('template_wizard_confirm_replace_confirm')}
          </Button>
          <Button
            variant="default"
            fullWidth
            onClick={() => {
              setReplaceConfirmOpen(false);
              setPendingSubmit(null);
            }}
          >
            {t('template_wizard_confirm_replace_cancel')}
          </Button>
        </Stack>
      </Modal>
    </>
  );
}
