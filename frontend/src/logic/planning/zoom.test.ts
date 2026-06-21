import { describe, expect, it } from 'vitest';

import { ZOOM_LEVELS, defaultZoomLevel, zoomIn, zoomOut } from './zoom';

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
