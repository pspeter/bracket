import { Anchor, Center } from '@mantine/core';
import { useTranslation } from 'react-i18next';

export function PublicFooter() {
  const { t } = useTranslation();
  return (
    <Center mt="xl" pb="md">
      <Anchor c="dimmed" href="/privacy" size="sm">
        {t('privacy_imprint_link')}
      </Anchor>
    </Center>
  );
}
