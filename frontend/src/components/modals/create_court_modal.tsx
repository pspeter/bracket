import { Button, Modal, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { GoPlus } from '@react-icons/all-files/go/GoPlus';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SWRResponse } from 'swr';

import { CourtsResponse } from '@openapi';
import { createCourt } from '@services/court';

export default function CourtModal({
  tournamentId,
  swrCourtsResponse,
  buttonSize,
  opened: controlledOpened,
  setOpened: controlledSetOpened,
}: {
  buttonSize?: 'xs' | 'lg';
  tournamentId: number;
  swrCourtsResponse: SWRResponse<CourtsResponse>;
  // When provided, the modal is controlled from outside (e.g. a toolbar menu)
  // and no trigger button is rendered.
  opened?: boolean;
  setOpened?: (opened: boolean) => void;
}) {
  const { t } = useTranslation();
  const [uncontrolledOpened, setUncontrolledOpened] = useState(false);
  const isControlled = controlledSetOpened != null;
  const opened = isControlled ? (controlledOpened ?? false) : uncontrolledOpened;
  const setOpened = isControlled ? controlledSetOpened : setUncontrolledOpened;
  const form = useForm({
    initialValues: {
      name: '',
    },

    validate: {
      name: (value) => (value.length > 0 ? null : t('too_short_name_validation')),
    },
  });

  return (
    <>
      <Modal opened={opened} onClose={() => setOpened(false)} title={t('add_court_title')}>
        <form
          onSubmit={form.onSubmit(async (values) => {
            await createCourt(tournamentId, values.name);
            await swrCourtsResponse.mutate();
            form.reset();
            setOpened(false);
          })}
        >
          <TextInput
            withAsterisk
            label={t('name_input_label')}
            placeholder={t('court_name_input_placeholder')}
            {...form.getInputProps('name')}
          />

          <Button fullWidth style={{ marginTop: 10 }} color="green" type="submit">
            {t('save_button')}
          </Button>
        </form>
      </Modal>
      {!isControlled && (
        <Button
          variant="outline"
          color="green"
          size={buttonSize}
          style={{ marginRight: 10 }}
          onClick={() => setOpened(true)}
          leftSection={<GoPlus size={24} />}
        >
          {t('add_court_title')}
        </Button>
      )}
    </>
  );
}
