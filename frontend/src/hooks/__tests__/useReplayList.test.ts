import { renderHook, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useReplayList } from '../useReplayList';

function mockResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('useReplayList', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches list with page and size on mount', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        mockResponse({ replays: [], page: 1, size: 10, total_items: 0, total_pages: 0 })
      );
    const { result } = renderHook(() => useReplayList({ authToken: 'tok' }));

    await waitFor(() => expect(result.current.loading).toBe(false));
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('page=1');
    expect(url).toContain('size=10');
    expect(url).not.toContain('player=');
    expect(result.current.data?.total_items).toBe(0);
  });

  it('search sets query and resets page to 1', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        mockResponse({ replays: [], page: 1, size: 10, total_items: 0, total_pages: 0 })
      );
    const { result } = renderHook(() => useReplayList({ authToken: 'tok' }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setPage(3));
    await waitFor(() => expect(result.current.page).toBe(3));

    act(() => result.current.search('seoungmun'));
    await waitFor(() => {
      expect(result.current.query).toBe('seoungmun');
      expect(result.current.page).toBe(1);
    });

    const lastUrl = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(lastUrl).toContain('player=seoungmun');
  });

  it('reset clears query and page', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      mockResponse({ replays: [], page: 1, size: 10, total_items: 0, total_pages: 0 })
    );
    const { result } = renderHook(() => useReplayList({ authToken: 'tok' }));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.search('x'));
    await waitFor(() => expect(result.current.query).toBe('x'));

    act(() => result.current.reset());
    await waitFor(() => {
      expect(result.current.query).toBe('');
      expect(result.current.page).toBe(1);
    });
  });

  it('does not fetch when authToken is null', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    renderHook(() => useReplayList({ authToken: null }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('captures error state on HTTP failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse({}, 500));
    const { result } = renderHook(() => useReplayList({ authToken: 'tok' }));
    await waitFor(() => expect(result.current.error).toBeTruthy());
  });
});
