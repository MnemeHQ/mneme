export function createSyntheticHost({
  delays = {},
  failOn = null,
  hangOn = null,
} = {}) {
  const calls = [];
  const timers = new Map();
  const hangResolvers = new Set();
  let cancelled = false;
  let activeCalls = 0;

  const read = async ({ key, delayMs } = {}) => {
    if (typeof key !== "string" || key.length === 0) {
      throw new Error("key must be a non-empty string");
    }
    activeCalls += 1;
    calls.push({ phase: "start", key });
    try {
      if (hangOn === key) {
        await new Promise((resolve, reject) => {
          hangResolvers.add({ resolve, reject });
        });
      } else {
        const delay = delayMs ?? delays[key] ?? 0;
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => {
            timers.delete(key);
            if (cancelled) reject(new Error("synthetic host cancelled"));
            else resolve();
          }, delay);
          timers.set(key, { timer, reject });
        });
      }
      if (cancelled) throw new Error("synthetic host cancelled");
      calls.push({ phase: "end", key });
      if (failOn === key) {
        throw new Error(`synthetic failure at ${key}`);
      }
      const sequence = calls.filter((call) => call.phase === "end").length;
      return { key, sequence };
    } finally {
      activeCalls -= 1;
    }
  };

  const cancelAll = () => {
    cancelled = true;
    for (const [key, entry] of timers) {
      clearTimeout(entry.timer);
      entry.reject(new Error(`synthetic host cancelled while waiting for ${key}`));
    }
    timers.clear();
    for (const entry of hangResolvers) {
      entry.reject(new Error("synthetic host cancelled while hanging"));
    }
    hangResolvers.clear();
  };

  return {
    read,
    cancelAll,
    calls,
    activeCalls: () => activeCalls,
    pendingTimers: () => timers.size,
  };
}
