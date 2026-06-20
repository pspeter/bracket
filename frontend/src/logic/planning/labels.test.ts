import { describe, expect, it } from 'vitest';

import { abbreviateStageItem, abbreviateTeamName, shortCourtLabel } from './labels';

describe('abbreviateTeamName', () => {
  it('keeps short names untouched', () => {
    expect(abbreviateTeamName('Red Sox')).toBe('Red Sox');
  });

  it('collapses repeated whitespace', () => {
    expect(abbreviateTeamName('Red   Sox ')).toBe('Red Sox');
  });

  it('shrinks trailing words to initials, keeping the first word', () => {
    expect(abbreviateTeamName('Ajax United')).toBe('Ajax U.');
  });

  it('keeps squad numbers intact while abbreviating', () => {
    expect(abbreviateTeamName('TSV Musterstadt 2')).toBe('TSV M. 2');
  });

  it('falls back to initials when the first word alone is too long', () => {
    expect(abbreviateTeamName('Sportvereinigung Musterhausen Altstadt')).toBe('SMA');
  });

  it('truncates a single long word with an ellipsis', () => {
    expect(abbreviateTeamName('Spielvereinigungsgemeinschaft')).toBe('Spielve…');
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
