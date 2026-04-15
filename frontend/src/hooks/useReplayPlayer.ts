import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReplayFrame } from '../types/replay';

interface UseReplayPlayerOptions {
  frames: ReplayFrame[];
}

interface UseReplayPlayerResult {
  currentFrame: number;
  isPlaying: boolean;
  speed: number;
  frame: ReplayFrame | null;
  totalFrames: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  next: () => void;
  prev: () => void;
  stepForward: (n: number) => void;
  seek: (index: number) => void;
  setSpeed: (speed: number) => void;
}

const ALLOWED_SPEEDS = [1, 2, 4, 8] as const;

export function useReplayPlayer({ frames }: UseReplayPlayerOptions): UseReplayPlayerResult {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeedState] = useState(1);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const totalFrames = frames.length;
  const atLast = currentFrame >= totalFrames - 1;

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => clearTimer, []);

  useEffect(() => {
    if (!isPlaying) {
      clearTimer();
      return;
    }
    if (atLast) {
      setIsPlaying(false);
      return;
    }
    clearTimer();
    timerRef.current = setTimeout(() => {
      setCurrentFrame((f) => Math.min(totalFrames - 1, f + 1));
    }, 1000 / speed);
    return clearTimer;
  }, [isPlaying, currentFrame, speed, totalFrames, atLast]);

  const play = useCallback(() => {
    if (totalFrames === 0) return;
    if (atLast) return;
    setIsPlaying(true);
  }, [atLast, totalFrames]);

  const pause = useCallback(() => setIsPlaying(false), []);
  const toggle = useCallback(() => {
    if (totalFrames === 0) return;
    if (atLast) return;
    setIsPlaying((p) => !p);
  }, [atLast, totalFrames]);

  const seek = useCallback(
    (index: number) => {
      if (totalFrames === 0) return;
      const clamped = Math.max(0, Math.min(totalFrames - 1, index));
      setCurrentFrame(clamped);
    },
    [totalFrames]
  );

  const next = useCallback(() => seek(currentFrame + 1), [currentFrame, seek]);
  const prev = useCallback(() => seek(currentFrame - 1), [currentFrame, seek]);
  const stepForward = useCallback((n: number) => seek(currentFrame + n), [currentFrame, seek]);

  const setSpeed = useCallback((next: number) => {
    if (ALLOWED_SPEEDS.includes(next as (typeof ALLOWED_SPEEDS)[number])) {
      setSpeedState(next);
    }
  }, []);

  const frame = totalFrames > 0 ? frames[Math.min(currentFrame, totalFrames - 1)] ?? null : null;

  return {
    currentFrame,
    isPlaying,
    speed,
    frame,
    totalFrames,
    play,
    pause,
    toggle,
    next,
    prev,
    stepForward,
    seek,
    setSpeed,
  };
}
