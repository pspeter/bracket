import { Alert, Center, Container, Stack, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import QRCode from 'react-qr-code';
import { useParams } from 'react-router';

import { getBaseURL } from '@components/utils/util';

export default function ScoreTrackingQrPage() {
  const { token } = useParams<{ token: string }>();
  const { t } = useTranslation();

  if (token == null || token.trim() === '') {
    return (
      <Container size="xs" py="xl">
        <Alert color="red">{t('score_tracking_invalid_link')}</Alert>
      </Container>
    );
  }

  const url = `${getBaseURL()}/score-tracking/${token}`;

  return (
    <Container size="sm" py="xl">
      <Stack align="center" gap="lg">
        <Title order={2}>{t('score_tracking_qr_heading')}</Title>
        <Center>
          <div style={{ background: 'white', padding: 24, borderRadius: 16 }}>
            <QRCode size={256} value={url} />
          </div>
        </Center>
      </Stack>
    </Container>
  );
}
