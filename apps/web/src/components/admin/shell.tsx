"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { adminRequest, reloadAdmin } from "@/lib/admin";
import { IngestionProvider } from "./ingestion-status";
import { Icon, Notice } from "./ui";

export function AdminShell({
  username,
  children,
}: {
  username: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const drawer = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const triggerButton = trigger.current;
    drawer.current?.querySelector<HTMLElement>("a")?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
      if (event.key === "Tab") {
        const items =
          drawer.current?.querySelectorAll<HTMLElement>("a, button");
        if (!items?.length) return;
        const first = items[0],
          last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", keydown);
      triggerButton?.focus();
    };
  }, [open]);
  function nav(
    href: string,
    label: string,
    icon: "home" | "settings" | "jobs" | "projects" | "skills" | "documents",
  ) {
    const active =
      pathname === href ||
      (href !== "/admin" && pathname.startsWith(`${href}/`));
    return (
      <Link
        href={href}
        onClick={() => setOpen(false)}
        className={`nav-item ${active ? "active" : ""}`}
        aria-current={
          active ? (pathname === href ? "page" : "location") : undefined
        }
      >
        <Icon name={icon} />
        {label}
      </Link>
    );
  }
  async function logout() {
    if (
      !window.confirm(
        "Sign out of the admin panel? Unsaved changes will be lost.",
      )
    )
      return;
    try {
      await adminRequest("logout", "POST");
      reloadAdmin("/admin/login");
    } catch (error) {
      setError((error as Error).message);
    }
  }
  return (
    <IngestionProvider>
      <div className="admin-shell">
        {open && (
          <button
            className="sidebar-backdrop"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          />
        )}
        <aside
          id="admin-sidebar"
          ref={drawer}
          className={`admin-sidebar ${open ? "is-open" : ""}`}
        >
          <Link href="/admin" className="brand" onClick={() => setOpen(false)}>
            <span className="brand-mark">
              <Icon name="spark" size={20} />
            </span>
            <span>
              Career AI<small>WORKSPACE</small>
            </span>
            <span className="admin-label">Admin</span>
          </Link>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {nav("/admin", "Home", "home")}
            {nav("/admin/jobs", "Jobs", "jobs")}
            {nav("/admin/projects", "Projects", "projects")}
            {nav("/admin/skills", "Skills", "skills")}
            {nav("/admin/documents", "Documents", "documents")}
            {nav("/admin/ingestion", "Ingestion Jobs", "documents")}
          </nav>
          <div className="sidebar-bottom">
            {nav("/admin/settings", "Settings", "settings")}
            <div className="account-row">
              <span className="avatar">
                {username.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <strong>{username}</strong>
                <small>Administrator</small>
              </div>
              <button
                className="icon-button"
                aria-label="Sign out"
                onClick={logout}
              >
                <Icon name="logout" />
              </button>
            </div>
            <Notice error>{error}</Notice>
          </div>
        </aside>
        <div className="admin-main" inert={open || undefined}>
          <div className="admin-topbar">
            <button
              ref={trigger}
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              aria-expanded={open}
              aria-controls="admin-sidebar"
              onClick={() => setOpen(true)}
            >
              <Icon name="menu" />
            </button>
            <span>
              Workspace<span className="breadcrumb-slash">/</span>
              <strong>
                {pathname === "/admin/settings" ||
                pathname.startsWith("/admin/settings/")
                  ? pathname === "/admin/settings/ai"
                    ? "Settings / AI Provider"
                    : "Settings"
                  : pathname.startsWith("/admin/ingestion")
                    ? "Ingestion Jobs"
                    : pathname.split("/")[2]
                      ? pathname.split("/")[2][0].toUpperCase() +
                        pathname.split("/")[2].slice(1)
                      : "Home"}
              </strong>
            </span>
            <span className="private-label">
              <Icon name="lock" size={13} />
              Private workspace
            </span>
          </div>
          <main>{children}</main>
        </div>
      </div>
    </IngestionProvider>
  );
}
