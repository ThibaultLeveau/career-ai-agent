"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import "./public-header.css";

export function PublicHeader({ actions, onHomeClick }: { actions?: ReactNode; onHomeClick?: () => void }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const disclosure = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const isExperience = /^\/(jobs|projects)(\/|$)/.test(pathname);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (!disclosure.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  function goHome() {
    setOpen(false);
    onHomeClick?.();
  }

  return (
    <header className="portfolio-header public-header">
      <Link className="portfolio-brand" href="/" aria-label="Thibault Leveau, home" onClick={goHome}>
        <BrandMark className="portfolio-logo" />
        <span>Thibault Leveau</span>
      </Link>
      <nav className="public-navigation" aria-label="Main navigation">
        <Link className="public-nav-link" href="/" aria-current={pathname === "/" ? "page" : undefined} onClick={goHome}>Home</Link>
        <div
          className="public-disclosure"
          ref={disclosure}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && open) {
              event.preventDefault();
              setOpen(false);
              trigger.current?.focus();
            }
          }}
        >
          <button
            className={`public-nav-link public-nav-trigger${isExperience ? " is-active" : ""}`}
            type="button"
            ref={trigger}
            aria-expanded={open}
            aria-controls={menuId}
            onClick={() => setOpen(!open)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setOpen(true);
                requestAnimationFrame(() => disclosure.current?.querySelector<HTMLAnchorElement>(".public-dropdown a")?.focus());
              }
            }}
          >
            Experiences
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <div className="public-dropdown" id={menuId} hidden={!open}>
            <span className="public-dropdown-label">EXPLORE MY WORK</span>
            <Link href="/jobs" aria-current={pathname.startsWith("/jobs") ? "page" : undefined} onClick={() => setOpen(false)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="7" width="18" height="14" rx="3" stroke="currentColor" strokeWidth="1.5" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12a23 23 0 0 0 18 0M12 11v4" stroke="currentColor" strokeWidth="1.5" /></svg>
              <span><strong>Jobs</strong><small>Roles, teams & experience</small></span><span className="public-dropdown-arrow" aria-hidden="true">↗</span>
            </Link>
            <Link href="/projects" aria-current={pathname.startsWith("/projects") ? "page" : undefined} onClick={() => setOpen(false)}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="2" stroke="currentColor" strokeWidth="1.5" /><rect x="14" y="3" width="7" height="7" rx="2" stroke="currentColor" strokeWidth="1.5" /><rect x="3" y="14" width="7" height="7" rx="2" stroke="currentColor" strokeWidth="1.5" /><path d="M14 17.5h7m-3.5-3.5v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              <span><strong>Projects</strong><small>Ideas, contributions & impact</small></span><span className="public-dropdown-arrow" aria-hidden="true">↗</span>
            </Link>
          </div>
        </div>
      </nav>
      <div className="portfolio-header-actions public-header-actions">{actions}<ThemeToggle /></div>
    </header>
  );
}
