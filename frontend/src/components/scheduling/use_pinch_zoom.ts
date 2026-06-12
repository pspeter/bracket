import { useCallback, useRef } from 'react';

import { PlannerEvent } from '@logic/planning/selection';

import { resolvePlannerAnchor } from './planner_anchor';

/** How much a pinch must scale before the grid snaps one zoom level. */
const PINCH_SNAP_RATIO = 1.3;
/** Accumulated ctrl+wheel delta that snaps one zoom level on desktop. */
const WHEEL_SNAP_DELTA = 80;

/**
 * Pinch (two fingers) and ctrl+wheel (desktop trackpad pinch / mouse wheel)
 * snap the planner between zoom levels. Returns a callback ref to put on the
 * element that should capture the gestures — attach it to the whole planning
 * page content (combined with `touch-action: pan-x pan-y`), so a pinch that
 * starts next to the grid zooms the schedule instead of the browser page.
 *
 * Native listeners because preventDefault is needed to keep the browser from
 * zooming the page instead; Safari additionally needs its proprietary gesture
 * events cancelled.
 */
export function usePinchZoom(onZoomEvent: (event: PlannerEvent) => void) {
  const onZoomEventRef = useRef(onZoomEvent);
  onZoomEventRef.current = onZoomEvent;
  const cleanupRef = useRef<(() => void) | null>(null);

  return useCallback((element: HTMLDivElement | null) => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    if (element == null) return;

    let pinchBaseline: number | null = null;
    let wheelAccumulated = 0;
    const distance = (touches: TouchList) =>
      Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);

    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length === 2) pinchBaseline = distance(event.touches);
    };
    const onTouchMove = (event: TouchEvent) => {
      if (event.touches.length !== 2 || pinchBaseline == null) return;
      event.preventDefault();
      const ratio = distance(event.touches) / pinchBaseline;
      if (ratio >= PINCH_SNAP_RATIO || ratio <= 1 / PINCH_SNAP_RATIO) {
        // Anchor the zoom on the pinch midpoint, measured before the level
        // changes, so the pinched region stays in view.
        const anchor = resolvePlannerAnchor(
          (event.touches[0].clientX + event.touches[1].clientX) / 2,
          (event.touches[0].clientY + event.touches[1].clientY) / 2
        );
        onZoomEventRef.current({
          type: ratio >= PINCH_SNAP_RATIO ? 'zoom-in' : 'zoom-out',
          anchor,
        });
        pinchBaseline = distance(event.touches);
      }
    };
    const onTouchEnd = () => {
      pinchBaseline = null;
    };
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      wheelAccumulated += event.deltaY;
      if (Math.abs(wheelAccumulated) >= WHEEL_SNAP_DELTA) {
        // Anchor the zoom on the pointer, so the region under the cursor
        // stays in view.
        const anchor = resolvePlannerAnchor(event.clientX, event.clientY);
        onZoomEventRef.current({
          type: wheelAccumulated < 0 ? 'zoom-in' : 'zoom-out',
          anchor,
        });
        wheelAccumulated = 0;
      }
    };
    // iOS Safari fires proprietary gesture events for pinches and zooms the
    // page unless they are cancelled; touch-action alone is not enough there.
    const onGesture = (event: Event) => event.preventDefault();

    element.addEventListener('touchstart', onTouchStart, { passive: true });
    element.addEventListener('touchmove', onTouchMove, { passive: false });
    element.addEventListener('touchend', onTouchEnd);
    element.addEventListener('wheel', onWheel, { passive: false });
    element.addEventListener('gesturestart', onGesture);
    element.addEventListener('gesturechange', onGesture);
    cleanupRef.current = () => {
      element.removeEventListener('touchstart', onTouchStart);
      element.removeEventListener('touchmove', onTouchMove);
      element.removeEventListener('touchend', onTouchEnd);
      element.removeEventListener('wheel', onWheel);
      element.removeEventListener('gesturestart', onGesture);
      element.removeEventListener('gesturechange', onGesture);
    };
  }, []);
}
