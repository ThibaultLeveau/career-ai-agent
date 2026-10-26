"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import { adminRequest } from "@/lib/admin";
import {
  activeStatus,
  sourceTypes,
  historySourceTypes,
  statusLabels,
  type IngestionJob,
  type SourceType,
} from "@/lib/ingestion";
import { StatusTooltip } from "./ingestion-status";
import { Notice } from "./ui";

type JobList = { items: IngestionJob[]; total: number };
type Log = { id: number; created_at: string; level: string; message: string };
const time = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "—";

function JobLogs({ jobId }: { jobId: number }) {
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    let cursor = 0;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (document.hidden) {
        timer = setTimeout(poll, 2000);
        return;
      }
      try {
        const [events, job] = await Promise.all([
          adminRequest<Log[]>(
            `ingestion/jobs/${jobId}/logs?after_id=${cursor}`,
          ),
          adminRequest<IngestionJob>(`ingestion/jobs/${jobId}`),
        ]);
        if (stopped) return;
        if (events.length) {
          cursor = events[events.length - 1].id;
          setLogs((current) => [...current, ...events]);
        }
        setError("");
        if (events.length === 200 || activeStatus(job.status))
          timer = setTimeout(poll, events.length === 200 ? 0 : 2000);
      } catch (error) {
        if (!stopped) {
          setError((error as Error).message);
          timer = setTimeout(poll, 10000);
        }
      }
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId]);
  return (
    <div className="ingestion-logs" aria-label={`Logs for ingestion ${jobId}`}>
      <Notice error>{error}</Notice>
      {!logs.length && !error && <p>Loading logs…</p>}
      <ol>
        {logs.map((log) => (
          <li key={log.id} className={`log-${log.level}`}>
            <time>{time(log.created_at)}</time>
            <span>{log.message}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function JobRow({
  job,
  expanded,
  toggle,
}: {
  job: IngestionJob;
  expanded: boolean;
  toggle: () => void;
}) {
  const type =
    job.source_type === "skills"
      ? "Skills (legacy)"
      : job.source_type[0].toUpperCase() + job.source_type.slice(1);
  return (
    <Fragment>
      <tr className={expanded ? "expanded" : undefined}>
        <td className="ingestion-source">
          {job.source_deleted ? (
            <span>{job.label}</span>
          ) : (
            <Link
              href={
                job.source_type === "skills"
                  ? "/admin/skills"
                  : `/admin/${job.source_type}/${job.record_id}`
              }
              title={job.label}
            >
              {job.label}
            </Link>
          )}
          <small>
            #{job.id} · {type}
            {job.source_deleted ? " · Deleted" : ""}
          </small>
        </td>
        <td>
          <StatusTooltip status={job.status} error={job.error} />
        </td>
        <td>
          <span>
            {job.completed_chunks}/{job.total_chunks} chunks
          </span>
          <small>{job.stage}</small>
          {activeStatus(job.status) && job.total_chunks > 0 && (
            <progress
              value={job.completed_chunks}
              max={job.total_chunks}
              aria-label="Embedding progress"
            />
          )}
        </td>
        <td>
          {job.retries}/{job.settings.ingestion.max_retries}
        </td>
        <td>{job.trigger.replaceAll("_", " ")}</td>
        <td>
          <time dateTime={job.created_at}>{time(job.created_at)}</time>
        </td>
        <td>
          <button
            type="button"
            className="icon-button"
            aria-label={`${expanded ? "Hide" : "View"} logs for ingestion ${job.id}`}
            aria-expanded={expanded}
            aria-controls={`ingestion-detail-${job.id}`}
            onClick={toggle}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
              style={{ transform: expanded ? "rotate(180deg)" : undefined }}
            >
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="ingestion-expanded">
          <td colSpan={7} id={`ingestion-detail-${job.id}`}>
            {job.error && <p className="ingestion-error">{job.error}</p>}
            {job.source_type === "skills" && (
              <p className="field-hint">
                Standalone skill ingestion is retired. Skill keywords are
                included in project documents.
              </p>
            )}
            <dl className="ingestion-details">
              <dt>Model</dt>
              <dd>
                {job.settings.embeddings.model} ·{" "}
                {job.settings.embeddings.dimensions} dimensions
              </dd>
              <dt>Chunking</dt>
              <dd>
                {job.settings.ingestion.chunk_size} tokens ·{" "}
                {job.settings.ingestion.chunk_overlap} overlap
              </dd>
              <dt>Started</dt>
              <dd>{time(job.started_at)}</dd>
              <dt>Finished</dt>
              <dd>{time(job.finished_at)}</dd>
              {job.status === "retrying" && (
                <>
                  <dt>Next attempt</dt>
                  <dd>{time(job.available_at)}</dd>
                </>
              )}
            </dl>
            <JobLogs key={job.id} jobId={job.id} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export function IngestionJobs({ initialJobId }: { initialJobId?: number }) {
  const [data, setData] = useState<JobList>({ items: [], total: 0 });
  const [loaded, setLoaded] = useState(false);
  const [sourceType, setSourceType] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<number | undefined>(initialJobId);
  const [selectedJob, setSelectedJob] = useState<IngestionJob | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<SourceType[]>([...sourceTypes]);
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
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
        const query = new URLSearchParams({
          offset: String(offset),
          limit: "25",
        });
        if (sourceType) query.set("source_type", sourceType);
        if (status) query.set("status", status);
        const result = await adminRequest<JobList>(`ingestion/jobs?${query}`);
        const selected = initialJobId
          ? await adminRequest<IngestionJob>(`ingestion/jobs/${initialJobId}`)
          : null;
        active =
          result.items.some((job) => activeStatus(job.status)) ||
          !!(selected && activeStatus(selected.status));
        if (!stopped) {
          setData(result);
          setSelectedJob(selected);
          setError("");
          setLoaded(true);
        }
      } catch (error) {
        if (!stopped) {
          setError((error as Error).message);
          setLoaded(true);
        }
      }
      if (!stopped) timer = setTimeout(poll, active ? 2000 : 10000);
    }
    const refresh = () => setVersion((value) => value + 1);
    const visible = () => {
      if (!document.hidden) refresh();
    };
    window.addEventListener("ingestion-updated", refresh);
    document.addEventListener("visibilitychange", visible);
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener("ingestion-updated", refresh);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [sourceType, status, offset, version, initialJobId]);
  async function reingest(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await adminRequest<{ queued: number; skipped: number }>(
        "ingestion/reingest",
        "POST",
        { source_types: selected },
      );
      setMessage(
        `Queued ${result.queued} items. Skipped ${result.skipped} already in progress.`,
      );
      setOffset(0);
      setVersion((value) => value + 1);
      dialog.current?.close();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="content-toolbar">
        <label>
          Content type
          <select
            value={sourceType}
            onChange={(e) => {
              setSourceType(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All types</option>
            {historySourceTypes.map((type) => (
              <option key={type} value={type}>
                {type === "skills"
                  ? "Skills (legacy)"
                  : type[0].toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {[
              "queued",
              "running",
              "retrying",
              "succeeded",
              "failed",
              "cancelled",
              "superseded",
            ].map((value) => (
              <option key={value} value={value}>
                {statusLabels[value]}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button button-primary"
          onClick={() => {
            setSelected([...sourceTypes]);
            dialog.current?.showModal();
          }}
        >
          Re-ingest all
        </button>
      </div>
      <Notice error>{error}</Notice>
      <Notice>{message}</Notice>
      <div
        className="ingestion-table-scroll"
        role="region"
        aria-label="Ingestion job history"
        tabIndex={0}
      >
        <table className="ingestion-table">
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Status</th>
              <th scope="col">Progress</th>
              <th scope="col">Retries</th>
              <th scope="col">Trigger</th>
              <th scope="col">Created</th>
              <th scope="col">
                <span className="sr-only">Logs</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {selectedJob &&
              !data.items.some((job) => job.id === selectedJob.id) && (
                <JobRow
                  job={selectedJob}
                  expanded={expanded === selectedJob.id}
                  toggle={() =>
                    setExpanded(
                      expanded === selectedJob.id ? undefined : selectedJob.id,
                    )
                  }
                />
              )}
            {data.items.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                expanded={expanded === job.id}
                toggle={() =>
                  setExpanded(expanded === job.id ? undefined : job.id)
                }
              />
            ))}
          </tbody>
        </table>
      </div>
      {!data.items.length && (
        <div className="content-empty">
          {loaded
            ? "No ingestion jobs match these filters."
            : "Loading ingestion jobs…"}
        </div>
      )}
      <div className="ingestion-pagination">
        <button
          className="button"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          Previous
        </button>
        <span>
          {data.total
            ? `${offset + 1}–${Math.min(offset + 25, data.total)} of ${data.total}`
            : "0 jobs"}
        </span>
        <button
          className="button"
          disabled={offset + 25 >= data.total}
          onClick={() => setOffset(offset + 25)}
        >
          Next
        </button>
      </div>
      <dialog
        ref={dialog}
        className="ingestion-dialog"
        aria-labelledby="reingest-title"
      >
        <form onSubmit={reingest}>
          <h2 id="reingest-title">Re-ingest content</h2>
          <p>
            Choose the content to rebuild using your saved settings. Items
            already processing will be skipped.
          </p>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={selected.length === sourceTypes.length}
              onChange={(e) =>
                setSelected(e.target.checked ? [...sourceTypes] : [])
              }
            />
            Select all
          </label>
          {sourceTypes.map((type) => (
            <label className="checkbox-label" key={type}>
              <input
                type="checkbox"
                checked={selected.includes(type)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, type]
                      : selected.filter((item) => item !== type),
                  )
                }
              />
              {type[0].toUpperCase() + type.slice(1)}
            </label>
          ))}
          <Notice error>{error}</Notice>
          <div className="ingestion-dialog-actions">
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="button button-primary"
              disabled={busy || !selected.length}
            >
              {busy ? "Queuing…" : "Start re-ingestion"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
