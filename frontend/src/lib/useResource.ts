import { useEffect, useRef, useState } from 'react';

/** Ignore stale responses on filter changes/unmounts; no response or data is fabricated. */
export function useResource<T>(key: string, load: () => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; error: unknown; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [attempt, setAttempt] = useState(0);
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    let active = true;
    setState({ data: null, error: null, loading: true });
    loader
      .current()
      .then((data) => {
        if (active) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (active) setState({ data: null, error, loading: false });
      });
    return () => {
      active = false;
    };
  }, [key, attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}
