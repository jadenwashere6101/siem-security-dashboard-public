import React, { forwardRef, useCallback, useEffect, useRef } from "react";

import { getWorkspaceNavigationBehavior } from "../utils/workspaceNavigation";
import "./MasterDetailLayout.css";

export function MasterDetailLayout({ detailOpen, children, ariaLabel = "Master detail workspace" }) {
  return (
    <div
      className={`master-detail-layout${detailOpen ? " master-detail-layout--open" : ""}`}
      aria-label={ariaLabel}
    >
      {children}
    </div>
  );
}

export function MasterDetailMaster({ children, ariaLabel = "Records" }) {
  return (
    <section className="master-detail-layout__master" aria-label={ariaLabel}>
      {children}
    </section>
  );
}

export const MasterDetailPane = forwardRef(function MasterDetailPane(
  { children, ariaLabel = "Selected record detail" },
  ref
) {
  return (
    <aside
      ref={ref}
      className="master-detail-layout__detail"
      aria-label={ariaLabel}
      tabIndex={-1}
    >
      {children}
    </aside>
  );
});

export function useMasterDetailFocus(selectionKey) {
  const detailRef = useRef(null);
  const triggerRef = useRef(null);
  const previousSelectionRef = useRef(null);

  const rememberTrigger = useCallback((element) => {
    triggerRef.current = element || null;
  }, []);

  const restoreTriggerFocus = useCallback(() => {
    if (triggerRef.current?.isConnected) {
      triggerRef.current.focus({ preventScroll: true });
    }
  }, []);

  useEffect(() => {
    if (selectionKey == null) {
      previousSelectionRef.current = null;
      return;
    }
    if (previousSelectionRef.current === selectionKey) return;
    previousSelectionRef.current = selectionKey;
    const pane = detailRef.current;
    if (!pane) return;

    pane.scrollIntoView?.({
      behavior: getWorkspaceNavigationBehavior(),
      block: "nearest",
      inline: "nearest",
    });
    const heading = pane.querySelector("h2, h3, [role='heading']");
    const focusTarget = heading || pane;
    if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
    focusTarget.focus({ preventScroll: true });
  }, [selectionKey]);

  return { detailRef, rememberTrigger, restoreTriggerFocus };
}
