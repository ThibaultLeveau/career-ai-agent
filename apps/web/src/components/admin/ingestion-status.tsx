"use client";

import Link from "next/link";
import { createPortal } from "react-dom";
import { ActionMenu } from "./action-menu";
import { Notice } from "./ui";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { adminRequest } from "@/lib/admin";
import {
  activeStatus,
  sourceTypes,
  statusLabels,
  type SourceType,
  type IngestionSummary,
  type IngestionJob,
} from "@/lib/ingestion";

type StatusMap = Partial<Record<SourceType, Record<string, IngestionSummary>>>;
const Context = createContext<{
  statuses: StatusMap;
  refresh: () => void;
  error: string;
}>({ statuses: {}, refresh: () => {}, error: "" });

export function IngestionProvider({ children }: { children: React.ReactNode }) {
  const [statuses, setStatuses] = useState<StatusMap>({});
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  useEffect(() => {
    window.addEventListener("ingestion-updated", refresh);
    return () => window.removeEventListener("ingestion-updated", refresh);
  }, [refresh]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (document.hidden) {
        timer = setTimeout(poll, 2000);
        return;
      }
      let active = false;
      try {
        const entries = await Promise.all(
          sourceTypes.map(
            async (type) =>
              [
                type,
                await adminRequest<Record<string, IngestionSummary>>(
                  `ingestion/status?source_type=${type}`,
                ),
              ] as const,
          ),
        );
        const next = Object.fromEntries(entries) as StatusMap;
        active = entries.some(([, items]) =>
          Object.values(items).some((item) => activeStatus(item.status)),
        );
        if (!stopped) {
          setStatuses(next);
          setError("");
        }
      } catch {
        if (!stopped) setError("Ingestion status is temporarily unavailable.");
      }
      if (!stopped) timer = setTimeout(poll, active ? 2000 : 10000);
    }
    void poll();
    const visible = () => {
      if (!document.hidden) refresh();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [version, refresh]);
  return (
    <Context.Provider value={{ statuses, refresh, error }}>
      {children}
    </Context.Provider>
  );
}

export function StatusIcon({ status }: { status: string }) {
  const active = activeStatus(status);
  return (
    <svg
      className={active ? "ingestion-spin" : ""}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      {active ? (
        <path d="M20 12a8 8 0 1 1-8-8" />
      ) : status === "succeeded" ? (
        <path d="m5 12 4 4L19 6" />
      ) : status === "failed" ? (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="m9 9 6 6m-6 0 6-6" />
        </>
      ) : (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6m0 3v1" />
        </>
      )}
    </svg>
  );
}

export function useIngestion({
  sourceType,
  recordId,
  initial,
}: {
  sourceType?: SourceType;
  recordId: number;
  initial?: IngestionSummary;
}) {
  const { statuses, refresh, error: statusError } = useContext(Context);
  const [submitted, setSubmitted] = useState<IngestionSummary>();
  const polled = sourceType ? statuses[sourceType]?.[recordId] : undefined;
  const current =
    (initial?.job_id ?? 0) > (polled?.job_id ?? 0)
      ? initial
      : (polled ?? initial);
  const value =
    (submitted?.job_id ?? 0) > (current?.job_id ?? 0) ? submitted : current;
  const status = value?.status ?? "not_ingested";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function reingest() {
    if (!sourceType) return;
    setBusy(true);
    setError("");
    try {
      const job = await adminRequest<IngestionJob>(
        `ingestion/${sourceType}/${recordId}/reingest`,
        "POST",
      );
      setSubmitted({
        status: job.status,
        job_id: job.id,
        stage: job.stage,
        error: job.error,
        completed_chunks: job.completed_chunks,
        total_chunks: job.total_chunks,
      });
      refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { value, status, busy, error, statusError, reingest };
}

export function StatusTooltip({
  status,
  error,
  href,
}: {
  status: string;
  error?: string | null;
  href?: string;
}) {
  const id = useId();
  const anchor = useRef<HTMLSpanElement>(null);
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  const label = `${statusLabels[status] ?? status}${error ? `: ${error}` : ""}`;
  function show() {
    const rect = anchor.current!.getBoundingClientRect();
    setPoint({
      x: Math.max(8, Math.min(rect.right - 240, innerWidth - 248)),
      y: rect.bottom + 6,
    });
  }
  return (
    <span
      ref={anchor}
      className="status-tooltip-anchor"
      onMouseEnter={show}
      onMouseLeave={() => setPoint(null)}
      onFocus={show}
      onBlur={() => setPoint(null)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setPoint(null);
      }}
    >
      {href ? (
        <Link
          className={`status-icon ingestion-${status}`}
          href={href}
          aria-label={label}
          aria-describedby={point ? id : undefined}
        >
          <StatusIcon status={status} />
        </Link>
      ) : (
        <span
          className={`status-icon ingestion-${status}`}
          tabIndex={0}
          role="img"
          aria-label={label}
          aria-describedby={point ? id : undefined}
        >
          <StatusIcon status={status} />
        </span>
      )}
      {point &&
        createPortal(
          <span
            id={id}
            role="tooltip"
            className="ingestion-tooltip"
            style={{ left: point.x, top: point.y }}
          >
            {label}
          </span>,
          document.querySelector(".admin") ?? document.body,
        )}
    </span>
  );
}

export function IngestionStatus(props: {
  sourceType: SourceType;
  recordId: number;
  initial?: IngestionSummary;
}) {
  const { value, status, busy, error, statusError, reingest } =
    useIngestion(props);
  return (
    <div className="editor-ingestion">
      <StatusTooltip
        status={status}
        error={value?.error || statusError}
        href={
          value?.job_id
            ? `/admin/ingestion?job=${value.job_id}`
            : "/admin/ingestion"
        }
      />
      <ActionMenu
        label="ingestion"
        actions={[
          {
            label: "Re-ingest",
            onSelect: reingest,
            disabled: busy || activeStatus(status),
          },
        ]}
      />
      <Notice error>{error}</Notice>
    </div>
  );
}
