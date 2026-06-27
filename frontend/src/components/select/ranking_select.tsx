import { Select } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { Ranking } from '@openapi';

import { getRankingTitle } from '@components/utils/rankings';

export function RankingSelect({ form, rankings }: { form: any; rankings: Ranking[] }) {
  const { t } = useTranslation();

  const data = rankings.map((ranking: Ranking, i: number) => ({
    value: ranking.id.toString(),
    label: `${getRankingTitle(ranking, t)} ${i === 0 ? `(${t('default_label')})` : ''}`.trim(),
  }));

  return (
    <Select
      withAsterisk
      data={data}
      label={t('ranking_title')}
      searchable
      allowDeselect={false}
      limit={16}
      mt={24}
      {...form.getInputProps('ranking_id')}
    />
  );
}
