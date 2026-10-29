"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminRequest } from "@/lib/admin";
import type { Timeline } from "@/lib/content";
import { Notice, useUnsavedChanges } from "../ui";

export function useEditor<T>(initial: T, collection: string, id?: number) {
  const router = useRouter();
  const [values, setValues] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [resetVersion, setResetVersion] = useState(0);
  const dirty = JSON.stringify(values) !== JSON.stringify(saved);
  useUnsavedChanges(dirty);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const invalidText = Object.entries(values as Record<string, unknown>).some(
      ([name, value]) => typeof value === "string" && Array.from(value).length > (name === "small_summary" ? 280 : 8000),
    );
    if (invalidText) {
      setError("Shorten the fields marked over their character limit before saving.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await adminRequest<{ id: number }>(
        id ? `${collection}/${id}` : collection,
        id ? "PUT" : "POST",
        values,
      );
      setSaved(values);
      setMessage("Changes saved.");
      if (!id) router.replace(`/admin/${collection}/${result.id}`);
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return {
    values,
    setValues,
    dirty,
    error,
    message,
    busy,
    resetVersion,
    submit,
    reset: () => {
      setValues(saved);
      setResetVersion((version) => version + 1);
      setError("");
      setMessage("");
    },
  };
}

export function Field({
  label,
  multiline,
  ...props
}: {
  label: string;
  multiline?: boolean;
  value: string;
  onChange: (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => void;
  required?: boolean;
  type?: string;
  maxLength?: number;
}) {
  return (
    <label>
      {label}
      {multiline ? (
        <textarea rows={4} maxLength={8000} {...props} />
      ) : (
        <input maxLength={200} {...props} />
      )}
    </label>
  );
}

export function TimelineFields({
  value,
  onChange,
}: {
  value: Timeline;
  onChange: (value: Partial<Timeline>) => void;
}) {
  return (
    <div className="timeline-fields">
      <div className="field-grid">
        <label>
          Start month
          <input
            type="month"
            min="1000-01"
            max={value.end_month || "9999-12"}
            value={value.start_month ?? ""}
            onChange={(e) => onChange({ start_month: e.target.value || null })}
          />
        </label>
        <label>
          End month
          <input
            type="month"
            min={value.start_month || "1000-01"}
            max="9999-12"
            disabled={value.ongoing}
            value={value.end_month ?? ""}
            onChange={(e) => onChange({ end_month: e.target.value || null })}
          />
        </label>
      </div>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={value.ongoing}
          onChange={(e) =>
            onChange({
              ongoing: e.target.checked,
              ...(e.target.checked ? { end_month: null } : {}),
            })
          }
        />{" "}
        Ongoing
      </label>
    </div>
  );
}

export function SaveBar({
  busy,
  dirty,
  isNew,
  reset,
  invalid = false,
  saving = busy,
}: {
  busy: boolean;
  dirty: boolean;
  isNew: boolean;
  reset: () => void;
  invalid?: boolean;
  saving?: boolean;
}) {
  return (
    <div className="save-bar">
      <span>
        {dirty
          ? "You have unsaved changes"
          : isNew
            ? "Ready when you are"
            : "All changes saved"}
      </span>
      <button
        type="button"
        className="button"
        disabled={busy || !dirty}
        onClick={reset}
      >
        Cancel
      </button>
      <button
        className="button button-primary"
        disabled={busy || invalid || (!isNew && !dirty)}
      >
        {saving ? "Saving…" : isNew ? "Create" : "Save changes"}
      </button>
    </div>
  );
}

export function DeleteButton({
  path,
  label,
  message,
  returnTo,
}: {
  path: string;
  label: string;
  message?: string;
  returnTo?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    if (!window.confirm(message ?? `Delete ${label}? This cannot be undone.`))
      return;
    setBusy(true);
    setError("");
    try {
      await adminRequest(path, "DELETE");
      if (returnTo) router.replace(returnTo);
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="delete-action">
      <button
        type="button"
        className="text-button danger-text"
        aria-label={`Delete ${label}`}
        disabled={busy}
        onClick={remove}
      >
        {busy ? "Deleting…" : "Delete"}
      </button>
      <Notice error>{error}</Notice>
    </div>
  );
}

export function ListToolbar({
  query,
  setQuery,
  label,
  href,
  children,
}: {
  query: string;
  setQuery: (query: string) => void;
  label: string;
  href?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="content-toolbar">
      <input
        type="search"
        aria-label={`Search ${label.toLowerCase()}`}
        placeholder={`Search ${label.toLowerCase()}…`}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {children}
      {href && (
        <Link className="button button-primary" href={href}>
          Add{" "}
          {label === "Jobs"
            ? "job"
            : label === "Projects"
              ? "project"
              : "document"}
        </Link>
      )}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="content-empty">{children}</div>;
}
