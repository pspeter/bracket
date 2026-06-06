import { Container } from '@mantine/core';
import React from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { DashboardFooter } from '@components/dashboard/footer';
import { DoubleHeader, getTournamentHeadTitle } from '@components/dashboard/layout';
import { setTitle } from '@components/utils/util';
import { getTournamentResponseByEndpointName } from '@services/dashboard';

export default function DashboardRulesPage() {
  const { t } = useTranslation();
  const tournamentDataFull = getTournamentResponseByEndpointName();
  const tournamentValid = !React.isValidElement(tournamentDataFull);

  if (!tournamentValid) {
    return tournamentDataFull;
  }

  setTitle(getTournamentHeadTitle(tournamentDataFull));

  return (
    <>
      <DoubleHeader tournamentData={tournamentDataFull} />
      <Container mt="1rem" px="sm" style={{ maxWidth: '56rem' }}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {tournamentDataFull.rules ?? ''}
        </ReactMarkdown>
      </Container>
      <DashboardFooter />
    </>
  );
}
