import React, { useCallback, useEffect, useRef, useState } from "react";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { readStoredSidebarCollapsed, writeStoredSidebarCollapsed } from "../utils/sidebarPreference";
import { NAVIGATION_DESTINATIONS, getWorkspaceNavigationBehavior } from "../utils/workspaceNavigation";
import { getViewportMode, theme, viewportModes } from "../theme";

function readViewportMode() {
  if (typeof window === "undefined") return viewportModes.desktop;
  return getViewportMode(window.innerWidth);
}

function SidebarLayout({
  sections,
  roleFlags,
  activeSectionId,
  onNavigate,
  title,
  eyebrow,
  navigationControls,
  topBarActions,
  statusLabel,
  versionLabel,
  navigationRequest = null,
  children,
}) {
  const [isCollapsed, setIsCollapsed] = useState(() => readStoredSidebarCollapsed() ?? false);
  const [viewportMode, setViewportMode] = useState(readViewportMode);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const mainRef = useRef(null);
  const toggleButtonRef = useRef(null);
  const handledNavigationNonceRef = useRef(null);
  const isOverlayMode = viewportMode !== viewportModes.desktop;

  const toggleCollapsed = useCallback(() => {
    if (isOverlayMode) {
      setIsMobileNavOpen((previous) => !previous);
      return;
    }
    setIsCollapsed((previous) => !previous);
  }, [isOverlayMode]);

  const closeMobileNav = useCallback(() => {
    setIsMobileNavOpen(false);
    window.requestAnimationFrame?.(() => toggleButtonRef.current?.focus());
  }, []);

  const handleNavigate = useCallback((sectionId) => {
    onNavigate(sectionId);
    if (isOverlayMode) {
      closeMobileNav();
    }
  }, [closeMobileNav, isOverlayMode, onNavigate]);

  useEffect(() => {
    writeStoredSidebarCollapsed(isCollapsed);
  }, [isCollapsed]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const onResize = () => {
      const nextMode = readViewportMode();
      setViewportMode(nextMode);
      if (nextMode === viewportModes.desktop) {
        setIsMobileNavOpen(false);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!isOverlayMode || !isMobileNavOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMobileNav();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeMobileNav, isMobileNavOpen, isOverlayMode]);

  useEffect(() => {
    const main = mainRef.current;
    if (!main || !navigationRequest || navigationRequest.sectionId !== activeSectionId) return;
    if (handledNavigationNonceRef.current === navigationRequest.nonce) return;
    if (navigationRequest.destination === NAVIGATION_DESTINATIONS.preserve) return;

    let cancelled = false;
    let frameId = null;
    let fallbackTimer = null;
    let observer = null;

    const completeNavigation = (allowTopFallback = false) => {
      if (cancelled || handledNavigationNonceRef.current === navigationRequest.nonce) return true;

      const requestedTarget = navigationRequest.destination === NAVIGATION_DESTINATIONS.element
        ? main.querySelector(`[data-navigation-target="${navigationRequest.targetKey}"]`)
        : null;
      if (
        navigationRequest.destination === NAVIGATION_DESTINATIONS.element &&
        !requestedTarget &&
        !allowTopFallback
      ) {
        return false;
      }

      const primaryHeading = main.querySelector("[data-workspace-heading], h1, h2, [role='heading']");
      const focusTarget = requestedTarget || primaryHeading || main;
      const mainRect = main.getBoundingClientRect();
      const targetRect = requestedTarget?.getBoundingClientRect();
      const hasRestoredScroll =
        navigationRequest.restoreScrollTop !== null &&
        navigationRequest.restoreScrollTop !== undefined &&
        Number.isFinite(Number(navigationRequest.restoreScrollTop));
      let top = 0;
      if (hasRestoredScroll) {
        top = Math.max(0, Number(navigationRequest.restoreScrollTop));
      } else if (targetRect) {
        top = Math.max(0, main.scrollTop + targetRect.top - mainRect.top);
      }

      if (typeof main.scrollTo === "function") {
        main.scrollTo({ top, left: 0, behavior: getWorkspaceNavigationBehavior() });
      } else {
        main.scrollTop = top;
      }
      if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
      focusTarget.focus({ preventScroll: true });
      handledNavigationNonceRef.current = navigationRequest.nonce;
      observer?.disconnect();
      if (fallbackTimer != null) window.clearTimeout(fallbackTimer);
      return true;
    };

    if (!completeNavigation()) {
      observer = new MutationObserver(() => {
        frameId = window.requestAnimationFrame(() => completeNavigation());
      });
      observer.observe(main, { childList: true, subtree: true });
      fallbackTimer = window.setTimeout(() => completeNavigation(true), 1000);
    }

    return () => {
      cancelled = true;
      if (frameId != null) window.cancelAnimationFrame(frameId);
      if (fallbackTimer != null) window.clearTimeout(fallbackTimer);
      observer?.disconnect();
    };
  }, [activeSectionId, navigationRequest]);

  const shellPadding = getShellPadding(viewportMode);

  return (
    <div style={shellStyle}>
      <TopBar
        isCollapsed={isOverlayMode ? !isMobileNavOpen : isCollapsed}
        onToggleCollapse={toggleCollapsed}
        title={title}
        eyebrow={eyebrow}
        navigationControls={navigationControls}
        viewportMode={viewportMode}
        toggleButtonRef={toggleButtonRef}
      >
        {topBarActions}
      </TopBar>

      <div style={bodyStyle}>
        {isOverlayMode && isMobileNavOpen ? (
          <button
            type="button"
            aria-label="Close navigation overlay"
            onClick={closeMobileNav}
            style={mobileBackdropStyle}
          />
        ) : null}
        <Sidebar
          sections={sections}
          roleFlags={roleFlags}
          activeSectionId={activeSectionId}
          onNavigate={handleNavigate}
          isCollapsed={isOverlayMode ? false : isCollapsed}
          isOverlay={isOverlayMode}
          isOpen={!isOverlayMode || isMobileNavOpen}
          statusLabel={statusLabel}
          versionLabel={versionLabel}
        />

        <main
          ref={mainRef}
          data-sidebar-state={getSidebarState(isOverlayMode, isCollapsed)}
          data-viewport-mode={viewportMode}
          style={{
            ...mainContentStyle,
            paddingLeft: shellPadding.inline,
            paddingRight: shellPadding.inline,
            paddingBottom: shellPadding.bottom,
          }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

function getSidebarState(isOverlayMode, isCollapsed) {
  if (isOverlayMode) return "overlay";
  return isCollapsed ? "collapsed" : "expanded";
}

function getShellPadding(viewportMode) {
  if (viewportMode === viewportModes.mobile) {
    return {
      inline: theme.spacing.shellMobile,
      bottom: theme.spacing.shellMobile,
    };
  }
  if (viewportMode === viewportModes.tablet) {
    return {
      inline: theme.spacing.shellTablet,
      bottom: theme.spacing.shellDesktop,
    };
  }
  return {
    inline: theme.spacing.shellDesktop,
    bottom: theme.spacing.shellDesktop,
  };
}

const shellStyle = {
  display: "flex",
  flexDirection: "column",
  height: "100vh",
  maxHeight: "100dvh",
  minHeight: 0,
  overflow: "hidden",
  backgroundColor: theme.color.bg,
};

const bodyStyle = {
  display: "flex",
  flex: "1 1 auto",
  minHeight: 0,
  overflow: "hidden",
  backgroundColor: theme.color.bg,
};

const mainContentStyle = {
  flex: "1 1 auto",
  minWidth: 0,
  minHeight: 0,
  overflow: "auto",
  paddingTop: "18px",
  paddingRight: "32px",
  paddingBottom: "32px",
  boxSizing: "border-box",
  backgroundColor: theme.color.bg,
};

const mobileBackdropStyle = {
  position: "fixed",
  inset: 0,
  zIndex: theme.zIndex.mobileBackdrop,
  border: "none",
  padding: 0,
  backgroundColor: "rgba(13, 17, 23, 0.58)",
  cursor: "pointer",
};

export default SidebarLayout;
