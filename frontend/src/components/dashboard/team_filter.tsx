import { Combobox, Input, InputBase, useCombobox } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

export interface TeamFilterOption {
  value: string;
  label: string;
}

/**
 * Searchable single-select for the public dashboard team filter. Mirrors the referee
 * combobox: it shows the (already capped at 100) team options and lets the user type to
 * narrow them down when there are more teams than fit comfortably in the list.
 */
export function TeamFilterCombobox({
  value,
  onChange,
  teamOptions,
  width,
}: {
  value: number | null;
  onChange: (teamId: number | null) => void;
  teamOptions: TeamFilterOption[];
  width?: number | string;
}) {
  const { t } = useTranslation();
  const combobox = useCombobox({
    onDropdownClose: () => combobox.resetSelectedOption(),
  });
  const [search, setSearch] = useState('');

  const currentLabel =
    value == null ? '' : (teamOptions.find((o) => o.value === `${value}`)?.label ?? '');

  const lowerSearch = search.toLowerCase().trim();
  const filteredTeams = teamOptions.filter((o) => o.label.toLowerCase().includes(lowerSearch));

  return (
    <Combobox
      store={combobox}
      onOptionSubmit={(val) => {
        onChange(val === '' ? null : parseInt(val, 10));
        setSearch('');
        combobox.closeDropdown();
      }}
    >
      <Combobox.Target>
        <InputBase
          size="xs"
          w={width}
          component="button"
          type="button"
          pointer
          rightSection={
            value != null ? (
              <Combobox.ClearButton onClear={() => onChange(null)} />
            ) : (
              <Combobox.Chevron />
            )
          }
          rightSectionPointerEvents={value != null ? 'all' : 'none'}
          onClick={() => combobox.openDropdown()}
        >
          {currentLabel || <Input.Placeholder>{t('filter_team_placeholder')}</Input.Placeholder>}
        </InputBase>
      </Combobox.Target>

      <Combobox.Dropdown>
        <Combobox.Search
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          placeholder={t('search_placeholder')}
        />
        <Combobox.Options mah={300} style={{ overflowY: 'auto' }}>
          {filteredTeams.length > 0 ? (
            filteredTeams.map((opt) => (
              <Combobox.Option key={opt.value} value={opt.value}>
                {opt.label}
              </Combobox.Option>
            ))
          ) : (
            <Combobox.Empty>{t('filter_team_no_options')}</Combobox.Empty>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  );
}
