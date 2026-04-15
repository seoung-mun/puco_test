import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useReplayPlayer } from '../useReplayPlayer';
import type { ReplayFrame } from '../../types/replay';

function makeFrames(n: number): ReplayFrame[] {
  return Array.from({ length: n }, (_, i) => ({
    turn: i,
    phase: 'role',
    actor_id: 'p1',
    action: { type: 'noop' },
    rich_state: null,
  }));
}

describe('useReplayPlayer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with currentFrame 0 and not playing', () => {
    const frames = makeFrames(5);
    const { result } = renderHook(() => useReplayPlayer({ frames }));
    expect(result.current.currentFrame).toBe(0);
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.totalFrames).toBe(5);
    expect(result.current.frame).toEqual(frames[0]);
  });

  it('next/prev moves within bounds', () => {
    const frames = makeFrames(3);
    const { result } = renderHook(() => useReplayPlayer({ frames }));
    act(() => result.current.next());
    expect(result.current.currentFrame).toBe(1);
    act(() => result.current.next());
    expect(result.current.currentFrame).toBe(2);
    act(() => result.current.next());
    expect(result.current.currentFrame).toBe(2); // clamped at last
    act(() => result.current.prev());
    expect(result.current.currentFrame).toBe(1);
  });

  it('seek clamps to bounds', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: makeFrames(5) }));
    act(() => result.current.seek(100));
    expect(result.current.currentFrame).toBe(4);
    act(() => result.current.seek(-10));
    expect(result.current.currentFrame).toBe(0);
  });

  it('play advances frames on timer at 1x', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: makeFrames(4) }));
    act(() => result.current.play());
    expect(result.current.isPlaying).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.currentFrame).toBe(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.currentFrame).toBe(2);
  });

  it('pauses automatically at last frame', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: makeFrames(2) }));
    act(() => result.current.play());
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    // Reached last frame; effect should set isPlaying false
    expect(result.current.currentFrame).toBe(1);
    expect(result.current.isPlaying).toBe(false);
  });

  it('setSpeed only accepts allowed values', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: makeFrames(3) }));
    act(() => result.current.setSpeed(2));
    expect(result.current.speed).toBe(2);
    act(() => result.current.setSpeed(3)); // not allowed
    expect(result.current.speed).toBe(2);
    act(() => result.current.setSpeed(8));
    expect(result.current.speed).toBe(8);
  });

  it('toggle flips play state', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: makeFrames(3) }));
    act(() => result.current.toggle());
    expect(result.current.isPlaying).toBe(true);
    act(() => result.current.toggle());
    expect(result.current.isPlaying).toBe(false);
  });

  it('play is no-op when frames empty', () => {
    const { result } = renderHook(() => useReplayPlayer({ frames: [] }));
    act(() => result.current.play());
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.frame).toBeNull();
  });
});
