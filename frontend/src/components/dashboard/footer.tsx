import { Anchor, Container, Group } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { BrandFooter } from '@components/navbar/_brand';
import classes from './footer.module.css';

const links = [
  { link: 'https://docs.bracketapp.nl', label: 'Website' },
  { link: 'https://github.com/evroon/bracket', label: 'GitHub' },
];

export function DashboardFooter() {
  const { t } = useTranslation();
  const items = links.map((link) => (
    <Anchor<'a'> c="dimmed" key={link.label} href={link.link} size="sm">
      {link.label}
    </Anchor>
  ));

  return (
    <div className={classes.footer}>
      <Container className={classes.inner}>
        <BrandFooter />
        <Group className={classes.links}>
          {items}
          <Anchor c="dimmed" href="/privacy" size="sm">
            {t('privacy_imprint_link')}
          </Anchor>
        </Group>
      </Container>
    </div>
  );
}
