import { useEffect } from 'react';

/**
 * Below this width we treat the device as a phone, matching `defaultZoomLevel`.
 */
const MOBILE_MAX_WIDTH_PX = 768;
/** Pins the page to 1:1 with browser zoom disabled while the planner is open. */
const LOCKED_VIEWPORT_CONTENT =
  'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no';

/**
 * Locks the browser's page zoom while the planning view is mounted on mobile.
 *
 * The planner captures pinch gestures on its content to switch between the
 * agenda/compact/overview zoom levels, so the browser's own pinch-zoom only
 * gets in the way: once the page drifts zoomed-in (on first paint, or after
 * iOS auto-zooms when a form field like the custom match duration is focused),
 * the content gesture handler eats the pinch and the only way back out is to
 * pinch on the navbar. Pinning the viewport to 1:1 with zooming disabled keeps
 * the page from ever zooming, leaving the planner's semantic zoom in sole
 * control. The original viewport meta is restored on unmount so the rest of
 * the app keeps normal accessibility zoom.
 */
export function useLockViewportZoom() {
  useEffect(() => {
    if (window.innerWidth >= MOBILE_MAX_WIDTH_PX) return undefined;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
    if (meta == null) return undefined;

    const previousContent = meta.getAttribute('content');
    meta.setAttribute('content', LOCKED_VIEWPORT_CONTENT);
    return () => {
      if (previousContent == null) meta.removeAttribute('content');
      else meta.setAttribute('content', previousContent);
    };
  }, []);
}
