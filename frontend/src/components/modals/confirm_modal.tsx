import { Button, Modal, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export function ConfirmModal({
  opened,
  setOpened,
  title,
  message,
  confirmLabel,
  onConfirm,
}: {
  opened: boolean;
  setOpened: (opened: boolean) => void;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  return (
    <Modal opened={opened} onClose={() => setOpened(false)} title={title}>
      <Stack gap="md">
        <Text size="sm">{message}</Text>
        <Button
          color="red"
          fullWidth
          loading={loading}
          onClick={async () => {
            setLoading(true);
            try {
              await onConfirm();
              setOpened(false);
            } finally {
              setLoading(false);
            }
          }}
        >
          {confirmLabel}
        </Button>
        <Button variant="default" fullWidth onClick={() => setOpened(false)}>
          {t('cancel_button')}
        </Button>
      </Stack>
    </Modal>
  );
}
