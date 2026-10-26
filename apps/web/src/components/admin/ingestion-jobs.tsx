"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { adminRequest } from "@/lib/admin";
import {
  activeStatus,
  sourceTypes,
  statusLabels,
  type IngestionJob,
  type SourceType,
} from "@/lib/ingestion";
import { StatusIcon } from "./ingestion-status";
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

function JobCard({
  job,
  expanded,
  toggle,
}: {
  job: IngestionJob;
  expanded: boolean;
  toggle: () => void;
}) {
  return (
    <article className="ingestion-job">
      <div className="ingestion-job-heading">
        <div>
          <small>
            #{job.id} · {job.source_type} · {job.trigger.replaceAll("_", " ")}
          </small>
          <h2>
            {job.source_deleted ? (
              job.label
            ) : (
              <Link
                href={
                  job.source_type === "skills"
                    ? "/admin/skills"
                    : `/admin/${job.source_type}/${job.record_id}`
                }
              >
                {job.label}
              </Link>
            )}
          </h2>
          {job.source_deleted && <small>Source deleted</small>}
        </div>
        <span className={`ingestion-state ingestion-${job.status}`}>
          <StatusIcon status={job.status} />
          {statusLabels[job.status]}
        </span>
      </div>
      <div className="ingestion-job-meta">
        <span>
          {job.completed_chunks}/{job.total_chunks} chunks
        </span>
        <span>
          Retries: {job.retries}/{job.settings.ingestion.max_retries}
        </span>
        <span>Stage: {job.stage}</span>
        <span>Created: {time(job.created_at)}</span>
      </div>
      {activeStatus(job.status) && job.total_chunks > 0 && (
        <progress
          value={job.completed_chunks}
          max={job.total_chunks}
          aria-label="Embedding progress"
        />
      )}
      {job.error && <p className="ingestion-error">{job.error}</p>}
      <button
        type="button"
        className="text-button"
        aria-expanded={expanded}
        onClick={toggle}
      >
        {expanded ? "Hide logs" : "View logs"}
      </button>
      {expanded && (
        <>
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
        </>
      )}
    </article>
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
            {sourceTypes.map((type) => (
              <option key={type} value={type}>
                {type[0].toUpperCase() + type.slice(1)}
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
      {selectedJob && !data.items.some((job) => job.id === selectedJob.id) && (
        <JobCard
          job={selectedJob}
          expanded={expanded === selectedJob.id}
          toggle={() =>
            setExpanded(
              expanded === selectedJob.id ? undefined : selectedJob.id,
            )
          }
        />
      )}
      <div className="ingestion-job-list">
        {data.items.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            expanded={expanded === job.id}
            toggle={() => setExpanded(expanded === job.id ? undefined : job.id)}
          />
        ))}
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
