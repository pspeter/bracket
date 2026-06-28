import { Center, Divider, Group, Stack, Text, Tooltip, UnstyledButton } from '@mantine/core';
import {
  Icon,
  IconBook,
  IconBrackets,
  IconBrandGithub,
  IconBrowser,
  IconCalendar,
  IconDeviceGamepad2,
  IconDots,
  IconHome,
  IconScoreboard,
  IconSettings,
  IconTrophy,
  IconUser,
  IconUsers,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

import PreloadLink from '@components/utils/link';
import { capitalize } from '@components/utils/util';
import { TournamentIssueEntry } from '@openapi';
import { getBaseApiUrl, getTournamentIssues } from '@services/adapter';
import classes from './_main_links.module.css';

type IssueSection = 'planning' | 'players' | 'score_tracking' | 'stages' | 'teams';

interface MainLinkProps {
  icon: Icon;
  label: string;
  link: string;
  links?: MainLinkProps[] | null;
  issueSection?: IssueSection;
  issueEntries?: TournamentIssueEntry[];
}

const ISSUE_TYPE_LABELS: Record<string, string> = {
  empty_slots: 'tournament_issue_empty_slots',
  not_finished_overdue: 'tournament_issue_not_finished_overdue',
  not_started_overdue: 'tournament_issue_not_started_overdue',
  players_without_team: 'tournament_issue_players_without_team',
  teams_below_min_size: 'tournament_issue_teams_below_min_size',
  unassigned_teams: 'tournament_issue_unassigned_teams',
  unplanned_matches: 'tournament_issue_unplanned_matches',
};

function issueCount(entries: TournamentIssueEntry[] = []) {
  return entries.reduce((sum, entry) => sum + entry.count, 0);
}

function formatIssueCount(count: number) {
  return count > 99 ? '99+' : `${count}`;
}

function IssueBadge({ count, mobile = false }: { count: number; mobile?: boolean }) {
  if (count === 0) {
    return null;
  }

  return (
    <span className={mobile ? classes.mobileIssueBadge : classes.issueBadge}>
      {formatIssueCount(count)}
    </span>
  );
}

function formatIssueBreakdown(
  entries: TournamentIssueEntry[] | undefined,
  t: (key: string, options?: Record<string, unknown>) => string
) {
  if (entries == null || entries.length === 0) {
    return '';
  }

  return entries
    .map((entry) => {
      const key = ISSUE_TYPE_LABELS[entry.type];
      if (key == null) {
        return `${entry.count} ${entry.type.replace(/_/g, ' ')}`;
      }
      return t(key, { count: entry.count });
    })
    .join(' · ');
}

function MainLinkMobile({ item, pathName }: { item: MainLinkProps; pathName: String }) {
  const count = issueCount(item.issueEntries);
  return (
    <>
      <UnstyledButton
        hiddenFrom="sm"
        component={PreloadLink}
        href={item.link}
        className={classes.mobileLink}
        style={{ width: '100%' }}
        data-active={pathName === item.link || undefined}
      >
        <Group className={classes.mobileLinkGroup}>
          <item.icon stroke={1.5} />
          <Text className={classes.mobileLinkLabel}>{item.label}</Text>
          <IssueBadge count={count} mobile />
        </Group>
        <Divider />
      </UnstyledButton>
    </>
  );
}

function MainLink({ item, pathName }: { item: MainLinkProps; pathName: String }) {
  const { t } = useTranslation();
  const count = issueCount(item.issueEntries);
  const breakdown = formatIssueBreakdown(item.issueEntries, t);
  const tooltipLabel =
    breakdown.length > 0 ? (
      <Stack gap={2}>
        <Text size="sm">{item.label}</Text>
        <Text size="xs" c="dimmed">
          {breakdown}
        </Text>
      </Stack>
    ) : (
      item.label
    );

  return (
    <>
      <Tooltip position="right" label={tooltipLabel} transitionProps={{ duration: 0 }}>
        <UnstyledButton
          visibleFrom="sm"
          component={PreloadLink}
          href={item.link}
          className={classes.link}
          data-active={pathName.startsWith(item.link) || undefined}
        >
          <span className={classes.iconWrap}>
            <item.icon stroke={1.5} />
            <IssueBadge count={count} />
          </span>
        </UnstyledButton>
      </Tooltip>
      <MainLinkMobile item={item} pathName={pathName} />
    </>
  );
}

export function getBaseLinksDict() {
  const { t } = useTranslation();

  return [
    { link: '/clubs', label: capitalize(t('clubs_title')), links: [], icon: IconUsers },
    { link: '/', label: capitalize(t('tournaments_title')), links: [], icon: IconHome },
    {
      link: '/user',
      label: t('user_title'),
      links: [],
      icon: IconUser,
    },
    {
      icon: IconDots,
      link: '',
      label: t('more_title'),
      links: [
        { link: 'https://docs.bracketapp.nl/', label: t('website_title'), icon: IconBrowser },
        {
          link: 'https://github.com/evroon/bracket',
          label: t('github_title'),
          icon: IconBrandGithub,
        },
        { link: `${getBaseApiUrl()}/docs`, label: t('api_docs_title'), icon: IconBook },
      ],
    },
  ];
}

export function getBaseLinks() {
  const location = useLocation();
  const pathName = location.pathname.replace(/\/+$/, '');
  return getBaseLinksDict()
    .filter((link) => link.links.length < 1)
    .map((link) => <MainLinkMobile key={link.label} item={link} pathName={pathName} />);
}

export function TournamentLinks({ tournament_id }: any) {
  const location = useLocation();
  const { t } = useTranslation();
  const tournamentId = Number(tournament_id);
  const issues = getTournamentIssues(tournamentId);
  const tm_prefix = `/tournaments/${tournamentId}`;
  const pathName = location.pathname.replace('[id]', tournament_id).replace(/\/+$/, '');

  const data: MainLinkProps[] = [
    {
      icon: IconSettings,
      label: capitalize(t('tournament_setting_title')),
      link: `${tm_prefix}/settings`,
    },
    {
      icon: IconScoreboard,
      label: capitalize(t('rankings_title')),
      link: `${tm_prefix}/rankings`,
    },
    {
      icon: IconUser,
      label: capitalize(t('players_title')),
      link: `${tm_prefix}/players`,
      issueSection: 'players',
    },
    {
      icon: IconUsers,
      label: capitalize(t('teams_title')),
      link: `${tm_prefix}/teams`,
      issueSection: 'teams',
    },
    {
      icon: IconTrophy,
      label: capitalize(t('stage_title')),
      link: `${tm_prefix}/stages`,
      issueSection: 'stages',
    },
    {
      icon: IconCalendar,
      label: capitalize(t('planning_title')),
      link: `${tm_prefix}/schedule`,
      issueSection: 'planning',
    },
    {
      icon: IconDeviceGamepad2,
      label: capitalize(t('score_tracking_title')),
      link: `${tm_prefix}/score-tracking`,
      issueSection: 'score_tracking',
    },
    {
      icon: IconBrackets,
      label: capitalize(t('results_title')),
      link: `${tm_prefix}/results`,
    },
  ];

  const links = data.map((link) => (
    <MainLink
      key={link.label}
      item={{
        ...link,
        issueEntries: link.issueSection == null ? [] : (issues.data?.data[link.issueSection] ?? []),
      }}
      pathName={pathName}
    />
  ));
  return (
    <>
      <Center hiddenFrom="sm">
        <h2>{capitalize(t('tournament_title'))}</h2>
      </Center>
      <Divider hiddenFrom="sm" />
      {links}
    </>
  );
}
