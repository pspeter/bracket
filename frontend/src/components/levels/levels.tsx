import { Badge, Select } from '@mantine/core';

import type { LevelResponse } from '@openapi';
import { stringToColour } from '@services/lookups';

export function getLevel(levels: LevelResponse[], levelId: number | null | undefined) {
  if (levelId == null) return null;
  return levels.find((level) => level.id === levelId) ?? null;
}

export function levelSelectData(levels: LevelResponse[], allLevelsLabel: string) {
  return [
    { value: 'all', label: allLevelsLabel },
    ...levels.map((level) => ({ value: `${level.id}`, label: level.name })),
  ];
}

export function LevelBadge({
  levels,
  levelId,
}: {
  levels: LevelResponse[];
  levelId: number | null | undefined;
}) {
  const level = getLevel(levels, levelId);
  if (level == null) return null;

  return (
    <Badge color={stringToColour(`level-${level.id}`)} variant="light">
      {level.name}
    </Badge>
  );
}

export function LevelFilterSelect({
  levels,
  value,
  onChange,
  label,
  placeholder,
  allLevelsLabel,
}: {
  levels: LevelResponse[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder: string;
  allLevelsLabel: string;
}) {
  if (levels.length === 0) return null;

  return (
    <Select
      label={label}
      placeholder={placeholder}
      value={value}
      data={levelSelectData(levels, allLevelsLabel)}
      onChange={(next) => onChange(next ?? 'all')}
    />
  );
}
