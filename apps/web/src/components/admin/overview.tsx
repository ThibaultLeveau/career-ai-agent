"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { adminRequest } from "@/lib/admin";
import { Icon, Notice } from "./ui";

export type OverviewData = {
  active: boolean;
  counts: { jobs: number; projects: number; skills: number; documents: number };
  ingestion: {
    pending: number;
    ongoing: number;
    failed: number;
    successful: number;
  };
};

const collections = ["jobs", "projects", "skills", "documents"] as const;
const stages = [
  {
    key: "pending",
    label: "Pending",
    description: "Queued or awaiting ingestion",
    color: "var(--warning)",
  },
  {
    key: "ongoing",
    label: "Ongoing",
    description: "Processing or retrying",
    color: "var(--info)",
  },
  {
    key: "failed",
    label: "Failed",
    description: "Needs your attention",
    color: "var(--danger)",
  },
  {
    key: "successful",
    label: "Successful",
    description: "Current and ready to retrieve",
    color: "var(--success)",
  },
] as const;

function Funnel({ counts }: { counts: OverviewData["ingestion"] }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return (
    <div className="funnel-layout">
      <div className="funnel-visual">
        <svg
          viewBox="0 0 560 340"
          role="img"
          aria-label={`Current ingestion: ${counts.pending} pending, ${counts.ongoing} ongoing, ${counts.failed} failed, ${counts.successful} successful`}
        >
          <path
            d="M280 104v25 M280 217v18 Q280 245 260 245H155Q140 245 140 263 M280 235Q280 245 300 245H405Q420 245 420 263"
            fill="none"
            stroke="var(--border-strong)"
            strokeWidth="1.5"
            strokeDasharray="4 5"
          />
          <path
            d="M40 20H520L455 106H105Z"
            fill="var(--surface-subtle)"
            stroke="var(--border-strong)"
          />
          <path
            d="M108 130H452L389 216H171Z"
            fill="var(--surface-subtle)"
            stroke="var(--border-strong)"
          />
          <rect
            x="28"
            y="264"
            width="224"
            height="68"
            rx="10"
            fill="var(--surface-subtle)"
            stroke="var(--border-strong)"
          />
          <rect
            x="308"
            y="264"
            width="224"
            height="68"
            rx="10"
            fill="var(--surface-subtle)"
            stroke="var(--border-strong)"
          />
          <text x="280" y="52" className="funnel-label" fill="var(--warning)">
            PENDING
          </text>
          <text x="280" y="84" className="funnel-value">
            {counts.pending}
          </text>
          <text x="280" y="162" className="funnel-label" fill="var(--info)">
            ONGOING
          </text>
          <text x="280" y="194" className="funnel-value">
            {counts.ongoing}
          </text>
          <text x="140" y="287" className="funnel-label" fill="var(--danger)">
            FAILED
          </text>
          <text x="140" y="317" className="funnel-value">
            {counts.failed}
          </text>
          <text x="420" y="287" className="funnel-label" fill="var(--success)">
            SUCCESSFUL
          </text>
          <text x="420" y="317" className="funnel-value">
            {counts.successful}
          </text>
        </svg>
      </div>
      <dl className="funnel-legend">
        {stages.map(({ key, label, description, color }) => (
          <div key={key}>
            <dt>
              <span className="funnel-dot" style={{ background: color }} />
              {label}
              <small>{description}</small>
            </dt>
            <dd>
              {counts[key]}
              <small>
                {total ? Math.round((counts[key] / total) * 100) : 0}%
              </small>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Overview({ initial }: { initial: OverviewData }) {
  const [data, setData] = useState(initial);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
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
        const next = await adminRequest<OverviewData>("overview");
        active = next.active;
        if (!stopped) {
          setData(next);
          setError("");
        }
      } catch {
        if (!stopped)
          setError(
            "The overview is temporarily unavailable. Showing the last known counts.",
          );
      }
      if (!stopped) timer = setTimeout(poll, active ? 2000 : 10000);
    }
    const refresh = () => setVersion((current) => current + 1);
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
  }, [version]);
  const total = Object.values(data.ingestion).reduce((a, b) => a + b, 0);
  return (
    <>
      <Notice error>{error}</Notice>
      <div className="overview-cards">
        {collections.map((type) => (
          <Link className="overview-card" href={`/admin/${type}`} key={type}>
            <div>
              <span>{type[0].toUpperCase() + type.slice(1)}</span>
              <Icon name={type} />
            </div>
            <strong>{data.counts[type]}</strong>
            <small>
              Manage {type}
              <Icon name="arrow" size={14} />
            </small>
          </Link>
        ))}
      </div>
      <section
        className="overview-ingestion"
        aria-labelledby="ingestion-overview-title"
      >
        <header>
          <div>
            <p className="eyebrow">KNOWLEDGE BASE</p>
            <h2 id="ingestion-overview-title">Ingestion overview</h2>
            <p>
              Current state of {total} {total === 1 ? "item" : "items"} · Jobs,
              projects and documents
            </p>
          </div>
          <Link className="button" href="/admin/ingestion">
            View ingestion jobs
            <Icon name="arrow" size={14} />
          </Link>
        </header>
        <Funnel counts={data.ingestion} />
        <footer>
          {total
            ? `${data.ingestion.successful} of ${total} items are up to date.`
            : "Add your first job, project or document to start building your knowledge base."}{" "}
          <span>Skills are included in project documents.</span>
        </footer>
      </section>
    </>
  );
}
