// Course-wide constants. Drives the dashboard mastery bar denominator etc.

export const TOTAL_SIGNS = 75;

/** Mock reference video for ALL signs in v1. Phase 2 replaces per-sign once we have real signer footage.
 *  Currently a nyan cat loop — paired with drill-phase pause behavior in ReferenceVideo to mock
 *  the "handshape → movement → full-sign" progression. */
export const MOCK_REFERENCE_VIDEO_URL = '/videos/nyan.mp4';

/** Final fallback if even the mock fails to load. */
export const FALLBACK_VIDEO_URL = '/videos/hello.mp4';

/** Localstorage key for App Settings (camera/reference/playback defaults). */
export const APP_SETTINGS_LS_KEY = 'asl-pilot.appSettings.v1';
