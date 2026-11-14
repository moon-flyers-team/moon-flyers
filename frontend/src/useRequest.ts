import { useEffect, useState } from 'react';

type Request<T> = (signal: AbortSignal) => Promise<T>;

// Callers memoize requests. Obsolete responses are hidden immediately and aborted.
export function useRequest<T>(request: Request<T> | null, delay = 350) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    request: Request<T> | null; attempt: number; data?: T; error?: string;
  }>({ request: null, attempt: 0 });
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      request(controller.signal).then(data => {
        if (!controller.signal.aborted) setState({ request, attempt, data });
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setState({
          request, attempt, error: error instanceof Error ? error.message : 'Request failed',
        });
      });
    }, delay);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [request, attempt, delay]);
  const current = state.request === request && state.attempt === attempt;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !!request && (!current || (!state.data && !state.error)),
    retry: () => setAttempt(value => value + 1),
  };
}
