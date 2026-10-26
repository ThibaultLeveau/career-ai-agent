"use client";

import { useEffect } from "react";

export function Icon({
  name,
  size = 18,
}: {
  name:
    | "jobs"
    | "projects"
    | "skills"
    | "documents"
    | "home"
    | "spark"
    | "settings"
    | "arrow"
    | "logout"
    | "menu"
    | "close"
    | "lock";
  size?: number;
}) {
  const paths = {
    jobs: "M3 7h18v14H3z M8 7V3h8v4 M3 12h18 M10 12v3h4v-3",
    projects: "M3 5h7l2 3h9v13H3z",
    skills: "M3 3h8l10 10-8 8L3 11z M7 7h.01",
    documents: "M5 3h9l5 5v13H5z M14 3v6h5 M8 13h8 M8 17h6",
    home: "m3 10 9-7 9 7 M5 9v12h14V9 M9 21v-8h6v8",
    spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z",
    settings:
      "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z",
    arrow: "M7 17 17 7 M7 7h10v10",
    logout: "M10 4H4v16h6 M10 12h11m-4-4 4 4-4 4",
    menu: "M4 6h16M4 12h16M4 18h16",
    close: "m6 6 12 12M6 18 18 6",
    lock: "M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4 M12 14v3",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

export function Notice({
  error,
  children,
}: {
  error?: boolean;
  children: React.ReactNode;
}) {
  if (!children) return null;
  return (
    <p
      className={`notice ${error ? "notice-error" : "notice-success"}`}
      role={error ? "alert" : "status"}
    >
      {children}
    </p>
  );
}

export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => event.preventDefault();
    const navigate = (event: MouseEvent) => {
      const link = (event.target as Element).closest("a");
      if (
        link &&
        link.href !== window.location.href &&
        !window.confirm("Discard your unsaved changes?")
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", navigate, true);
    };
  }, [dirty]);
}

export function PageTitle({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <header className="page-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{children}</p>
    </header>
  );
}
