import { describe, expect, it } from 'vitest';

import {
  ZOOM_LEVELS,
  abbreviateTeamName,
  defaultZoomLevel,
  levelColour,
  shortCourtLabel,
  zoomIn,
  zoomOut,
} from './zoom';

describe('zoom levels', () => {
  it('orders the three levels from most detailed to most zoomed out', () => {
    expect(ZOOM_LEVELS).toEqual(['agenda', 'compact', 'overview']);
  });

  it('zoomIn steps toward agenda and stops there', () => {
    expect(zoomIn('overview')).toBe('compact');
    expect(zoomIn('compact')).toBe('agenda');
    expect(zoomIn('agenda')).toBe('agenda');
  });

  it('zoomOut steps toward overview and stops there', () => {
    expect(zoomOut('agenda')).toBe('compact');
    expect(zoomOut('compact')).toBe('overview');
    expect(zoomOut('overview')).toBe('overview');
  });
});

describe('defaultZoomLevel', () => {
  it('opens phones at agenda', () => {
    expect(defaultZoomLevel(375)).toBe('agenda');
    expect(defaultZoomLevel(767)).toBe('agenda');
  });

  it('opens tablets and desktops at compact', () => {
    expect(defaultZoomLevel(768)).toBe('compact');
    expect(defaultZoomLevel(1024)).toBe('compact');
    expect(defaultZoomLevel(1920)).toBe('compact');
  });
});

describe('abbreviateTeamName', () => {
  it('keeps short names untouched', () => {
    expect(abbreviateTeamName('Smash Bros')).toBe('Smash Bros');
  });

  it('collapses repeated whitespace', () => {
    expect(abbreviateTeamName('Smash   Bros ')).toBe('Smash Bros');
  });

  it('shrinks trailing words to initials, keeping the first word', () => {
    expect(abbreviateTeamName('Smash Brothers United')).toBe('Smash B. U.');
  });

  it('keeps squad numbers intact while abbreviating', () => {
    expect(abbreviateTeamName('TSV Musterstadt 2')).toBe('TSV M. 2');
  });

  it('falls back to initials when the first word alone is too long', () => {
    expect(abbreviateTeamName('Sportvereinigung Musterhausen Altstadt')).toBe('SMA');
  });

  it('truncates a single long word with an ellipsis', () => {
    expect(abbreviateTeamName('Spielvereinigungsgemeinschaft')).toBe('Spielverein…');
  });
});

describe('shortCourtLabel', () => {
  it('uses the trailing number when the court is numbered', () => {
    expect(shortCourtLabel('Court 12')).toBe('12');
    expect(shortCourtLabel('Feld 3')).toBe('3');
  });

  it('uses word initials for unnumbered multi-word names', () => {
    expect(shortCourtLabel('Center Court')).toBe('CC');
  });

  it('uses a short prefix for unnumbered single-word names', () => {
    expect(shortCourtLabel('Arena')).toBe('Ar');
  });
});

describe('levelColour', () => {
  const levels = [
    { id: 7, name: 'Beginners', position: 0 },
    { id: 3, name: 'Intermediate', position: 1 },
    { id: 9, name: 'Pros', position: 2 },
  ];

  it('assigns distinct, stable colours by level position', () => {
    const colours = levels.map((level) => levelColour(level.id, levels));
    expect(new Set(colours).size).toBe(3);
    expect(levelColour(3, levels)).toBe(levelColour(3, levels));
  });

  it('ignores list order, keyed by position', () => {
    const shuffled = [levels[2], levels[0], levels[1]];
    expect(levelColour(7, shuffled)).toBe(levelColour(7, levels));
  });

  it('degrades to gray for matches without a level', () => {
    expect(levelColour(null, levels)).toBe('gray');
  });

  it('degrades to gray for unknown levels', () => {
    expect(levelColour(42, levels)).toBe('gray');
  });
});
