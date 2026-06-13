import { describe, expect, it } from 'vitest';

import {
  ZOOM_LEVELS,
  abbreviateStageItem,
  abbreviateTeamName,
  defaultZoomLevel,
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

describe('abbreviateStageItem', () => {
  it('keeps a short trailing letter or number', () => {
    expect(abbreviateStageItem('Group C')).toBe('C');
    expect(abbreviateStageItem('Group 10')).toBe('10');
  });

  it('uses word initials when the trailing word is long', () => {
    expect(abbreviateStageItem('Winners Bracket')).toBe('WB');
  });

  it('truncates a single long word', () => {
    expect(abbreviateStageItem('Quarterfinals')).toBe('Qua');
  });

  it('leaves a single short word intact', () => {
    expect(abbreviateStageItem('Pool')).toBe('Pool');
  });
});
