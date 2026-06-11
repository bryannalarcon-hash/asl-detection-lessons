/**
 * Regression spec for useCameraPermission failure-mode handling.
 *
 * Bug (prod, Firefox): every getUserMedia failure collapsed into a single
 * dead-end `unsupported` state with the message "Camera not available on this
 * device or browser", even when the real cause was (a) the camera being held
 * by another app/tab (NotReadableError / AbortError — retryable), (b) an
 * insecure http:// context where Firefox hides navigator.mediaDevices
 * entirely, or (c) an overconstrained request that would succeed with bare
 * `{video: true}` constraints. The user saw "unsupported" on hardware that
 * worked the day before, with no retry affordance.
 *
 * These tests pin the contract: the unsupported state must carry a `reason`
 * discriminator, and OverconstrainedError must auto-fall back to `{video:true}`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCameraPermission } from '@/hooks/useCameraPermission';

function namedError(name: string, message = ''): Error {
  const err = new Error(message);
  err.name = name;
  return err;
}

function fakeStream(): MediaStream {
  return {
    getTracks: () => [],
    getVideoTracks: () => [],
  } as unknown as MediaStream;
}

/** Install a mock mediaDevices.getUserMedia; returns the mock fn. */
function mockGetUserMedia(impl: (c: MediaStreamConstraints) => Promise<MediaStream>) {
  const fn = vi.fn(impl);
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: fn },
  });
  return fn;
}

function removeMediaDevices() {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: undefined,
  });
}

function setSecureContext(value: boolean) {
  Object.defineProperty(window, 'isSecureContext', {
    configurable: true,
    value,
  });
}

const originalMediaDevices = Object.getOwnPropertyDescriptor(
  Navigator.prototype,
  'mediaDevices'
);

beforeEach(() => {
  setSecureContext(true);
});

afterEach(() => {
  vi.restoreAllMocks();
  // Drop the per-test instance property so the prototype getter (or absence)
  // is restored for the next test.
  delete (navigator as unknown as Record<string, unknown>).mediaDevices;
  if (originalMediaDevices) {
    Object.defineProperty(Navigator.prototype, 'mediaDevices', originalMediaDevices);
  }
});

describe('useCameraPermission failure modes', () => {
  it('NotReadableError (camera held by another app) → unsupported with reason "in-use"', async () => {
    mockGetUserMedia(() => Promise.reject(namedError('NotReadableError')));
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('unsupported');
    expect(
      (result.current.state as { reason?: string }).reason
    ).toBe('in-use');
  });

  it('AbortError (Firefox "Starting videoinput failed") → unsupported with reason "in-use"', async () => {
    mockGetUserMedia(() => Promise.reject(namedError('AbortError')));
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('unsupported');
    expect(
      (result.current.state as { reason?: string }).reason
    ).toBe('in-use');
  });

  it('no mediaDevices on an insecure context → reason "insecure-context"', async () => {
    removeMediaDevices();
    setSecureContext(false);
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('unsupported');
    expect(
      (result.current.state as { reason?: string }).reason
    ).toBe('insecure-context');
  });

  it('no mediaDevices on a secure context → reason "no-api"', async () => {
    removeMediaDevices();
    setSecureContext(true);
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('unsupported');
    expect(
      (result.current.state as { reason?: string }).reason
    ).toBe('no-api');
  });

  it('NotFoundError → reason "no-device"', async () => {
    mockGetUserMedia(() => Promise.reject(namedError('NotFoundError')));
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('unsupported');
    expect(
      (result.current.state as { reason?: string }).reason
    ).toBe('no-device');
  });

  it('OverconstrainedError on sized constraints → auto-falls back to {video:true} and grants', async () => {
    const stream = fakeStream();
    const fn = mockGetUserMedia((c) => {
      const video = c.video;
      if (typeof video === 'object' && video !== null && 'width' in video) {
        return Promise.reject(namedError('OverconstrainedError'));
      }
      return Promise.resolve(stream);
    });
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    await waitFor(() => {
      expect(result.current.state.kind).toBe('granted');
    });
    expect(fn).toHaveBeenCalledTimes(2);
    expect(fn.mock.calls[1][0]).toEqual({ video: true, audio: false });
  });

  it('NotAllowedError still maps to denied (no regression)', async () => {
    mockGetUserMedia(() => Promise.reject(namedError('NotAllowedError')));
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('denied');
  });

  it('success path still grants (no regression)', async () => {
    const stream = fakeStream();
    mockGetUserMedia(() => Promise.resolve(stream));
    const { result } = renderHook(() => useCameraPermission());
    await act(async () => {
      await result.current.request();
    });
    expect(result.current.state.kind).toBe('granted');
  });
});
