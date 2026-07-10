import React, { createContext, useCallback, useContext, useMemo, useRef } from "react";

const ResponseSyncContext = createContext({
  publishMutation: () => {},
  subscribe: () => () => {},
});

/**
 * Lightweight pub/sub for canonical response mutation invalidation keys.
 * Panels subscribe and quietly refetch when overlapping keys are published.
 */
export function ResponseSyncProvider({ children }) {
  const listenersRef = useRef(new Set());

  const publishMutation = useCallback((keys = [], meta = {}) => {
    const normalized = Array.isArray(keys)
      ? keys.map((key) => String(key))
      : [];
    // Always include aggregate keys so registry/blocklist listeners refresh.
    const withAggregates = Array.from(
      new Set([...normalized, "response_registry", "blocklist"])
    );
    listenersRef.current.forEach((listener) => {
      try {
        listener(withAggregates, meta);
      } catch (error) {
        // Keep other subscribers healthy if one panel throws.
        console.error("Response sync listener failed", error);
      }
    });
  }, []);

  const subscribe = useCallback((listener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const value = useMemo(
    () => ({ publishMutation, subscribe }),
    [publishMutation, subscribe]
  );

  return (
    <ResponseSyncContext.Provider value={value}>
      {children}
    </ResponseSyncContext.Provider>
  );
}

export function useResponseSync() {
  return useContext(ResponseSyncContext);
}

export function keysOverlap(publishedKeys, watchedKeys) {
  if (!Array.isArray(publishedKeys) || !Array.isArray(watchedKeys)) {
    return false;
  }
  const published = new Set(publishedKeys.map(String));
  return watchedKeys.some((key) => published.has(String(key)));
}
