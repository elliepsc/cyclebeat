import { useEffect, useState } from "react";

// After this long a pending call is almost certainly a cold start, not a hiccup.
export const SLOW_NOTICE_AFTER_MS = 5_000;

export function useSlowNotice(pending: boolean, afterMs = SLOW_NOTICE_AFTER_MS): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (!pending) return;
    const timer = setTimeout(() => setSlow(true), afterMs);
    return () => clearTimeout(timer);
  }, [pending, afterMs]);
  return slow;
}
