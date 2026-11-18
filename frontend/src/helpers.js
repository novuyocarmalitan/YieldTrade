import { useCallback, useEffect, useState } from "react";

export const money = (n) => `$${Number(n).toFixed(2)}`;
export const kg = (n) => `${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })} kg`;

const day = (offsetDays = 0) => new Date(Date.now() + offsetDays * 864e5).toISOString().slice(0, 10);
export const today = () => day(0);
export const inDays = (n) => day(n);

/** Load something on mount and whenever `deps` change. Returns {data, error, loading, reload}. */
export function useFetch(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: "", loading: true });
  // The caller lists the real dependencies; the loader closure is rebuilt only when they change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(loader, deps);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    run()
      .then((data) => live && setState({ data, error: "", loading: false }))
      .catch((e) => live && setState({ data: null, error: e, loading: false }));
    return () => {
      live = false;
    };
  }, [run, tick]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}
