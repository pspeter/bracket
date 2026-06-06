import { Alert, Center, Container, Stack, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import QRCode from 'react-qr-code';
import { useParams } from 'react-router';

import { getBaseURL } from '@components/utils/util';

export default function DashboardQrPage() {
  const { endpoint } = useParams<{ endpoint: string }>();
  const { t } = useTranslation();

  if (endpoint == null || endpoint.trim() === '') {
    return (
      <Container size="xs" py="xl">
        <Alert color="red">{t('dashboard_qr_invalid_link')}</Alert>
      </Container>
    );
  }

  const dashboardUrl = `${getBaseURL()}/tournaments/${endpoint}/dashboard`;

  return (
    <Container size="sm" py="xl">
      <Stack align="center" gap="lg">
        <Title order={2}>{t('dashboard_qr_heading')}</Title>
        <Center>
          <div
            style={{
              background: 'white',
              padding: 24,
              borderRadius: 16,
            }}
          >
            <QRCode size={256} value={dashboardUrl} />
          </div>
        </Center>
      </Stack>
    </Container>
  );
}
