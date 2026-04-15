import { useCallback, useEffect, useState } from 'react';
import type { ReplayListResponse } from '../types/replay';

interface UseReplayListOptions {
  authToken: string | null;
  pageSize?: number;
}

interface UseReplayListResult {
  data: ReplayListResponse | null;
  loading: boolean;
  error: string | null;
  page: number;
  query: string;
  setPage: (page: number) => void;
  search: (query: string) => void;
  reset: () => void;
  refresh: () => void;
}

export function useReplayList({
  authToken,
  pageSize = 10,
}: UseReplayListOptions): UseReplayListResult {
  const [data, setData] = useState<ReplayListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!authToken) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('size', String(pageSize));
    if (query) params.set('player', query);

    fetch(`/api/puco/replays/?${params.toString()}`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as ReplayListResponse;
      })
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [authToken, page, pageSize, query, refreshTick]);

  const search = useCallback((next: string) => {
    setQuery(next.trim());
    setPage(1);
  }, []);

  const reset = useCallback(() => {
    setQuery('');
    setPage(1);
  }, []);

  const refresh = useCallback(() => setRefreshTick((n) => n + 1), []);

  return { data, loading, error, page, query, setPage, search, reset, refresh };
}
