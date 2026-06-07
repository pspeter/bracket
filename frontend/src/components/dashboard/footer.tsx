import { Anchor, Container, Group } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { BrandFooter } from '@components/navbar/_brand';
import classes from './footer.module.css';

export function DashboardFooter() {
  const { t } = useTranslation();

  return (
    <div className={classes.footer}>
      <Container className={classes.inner}>
        <BrandFooter />
        <Group className={classes.links}>
          <Anchor c="dimmed" href="/privacy" size="sm">
            {t('privacy_imprint_link')}
          </Anchor>
        </Group>
      </Container>
    </div>
  );
}
