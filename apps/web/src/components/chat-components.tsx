"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChatAnswer } from "@/components/chat-answer";
import { isChatComponent, type CareerListData, type ChatComponent, type DetailAction, type JobCardData, type JobRow, type ProjectCardData, type ProjectRow, type ResumeDownloadData } from "@/lib/chat-components";

type OpenRecord = (question: string, action: DetailAction) => void;
type ViewProps = { data: ChatComponent; busy: boolean; onOpen: OpenRecord; onUpdate: (data: CareerListData) => void };

function date(month: string | null) {
  if (!month) return "Date unspecified";
  return new Intl.DateTimeFormat("en", { month: "short", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${month}-01T00:00:00Z`));
}

function Period({ record }: { record: ProjectRow | JobRow }) {
  return <span className="career-period">{date(record.start_month)}{record.ongoing ? " – Present" : record.end_month ? ` – ${date(record.end_month)}` : ""}</span>;
}

function Skills({ skills }: { skills: string[] }) {
  if (!skills.length) return null;
  return <ul className="career-skills" aria-label="Associated skills">{skills.map((skill) => <li key={skill}>{skill}</li>)}</ul>;
}

function KnowMore({ record, disabled, onOpen }: { record: ProjectRow | JobRow; disabled: boolean; onOpen: OpenRecord }) {
  const label = "name" in record ? record.name : `${record.title} at ${record.company}`;
  return <button type="button" className="career-more" disabled={disabled}
    aria-label={`Know more about ${label}`}
    onClick={() => onOpen(`Tell me more about ${label}.`, record.action)}>
    <strong aria-hidden="true">✳</strong> know more ...
  </button>;
}

function CareerList({ data: initial, busy: chatBusy, onOpen, onUpdate }: ViewProps & { data: CareerListData }) {
  const [data, setData] = useState(initial);
  const [filter, setFilter] = useState(initial.filter);
  const [query, setQuery] = useState<{ token: string; filter: string; page: number; delay: number; show_all: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const update = useRef(onUpdate);
  const filterId = useId();
  useEffect(() => { update.current = onUpdate; }, [onUpdate]);
  useEffect(() => {
    if (!query) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch("/api/chat/components/page", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: query.token, filter: query.filter, page: query.page, show_all: query.show_all }),
          signal: controller.signal, cache: "no-store",
        });
        const result: unknown = await response.json();
        if (!response.ok || !isChatComponent(result) || !("items" in result) || result.type !== initial.type)
          throw new Error("This list could not be loaded. Please try again.");
        if (!controller.signal.aborted) {
          setData(result);
          update.current(result);
        }
      } catch {
        if (!controller.signal.aborted) setError("This list could not be loaded. Please try again.");
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }, query.delay);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, initial.type]);

  function load(value: string, page: number, delay = 0, showAll = false) {
    setError("");
    setBusy(true);
    setQuery({ token: data.token, filter: value, page, delay, show_all: showAll });
  }
  const projects = data.type === "project_list";
  const label = projects ? "Projects" : "Jobs";
  const filtered = data.filtered || Boolean(data.filter);
  const catalogTotal = data.unfiltered_total ?? data.total;
  const start = data.matched_total ? (data.page - 1) * data.page_size + 1 : 0;
  const end = start ? start + data.items.length - 1 : 0;
  const pages = Math.max(1, Math.ceil(data.matched_total / data.page_size));
  return <section className={`career-list ${projects ? "career-project-list" : "career-job-list"}`} aria-label={`${label} list`} aria-busy={busy}>
    <div className="career-list-toolbar">
      <div><span className="career-eyebrow">EXPLORE MY WORK</span><h3>{label} <span>{filtered ? data.matched_total : data.total}</span></h3>{data.scope_label && <p className="career-scope-label">{data.scope_label}</p>}</div>
      <label htmlFor={filterId} className="career-filter"><span className="sr-only">Filter {label.toLowerCase()}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" width="16" height="16" fill="none"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" /><path d="m13 13 4 4" stroke="currentColor" /></svg>
        <input id={filterId} type="text" value={filter} maxLength={200} disabled={busy && query?.show_all} placeholder={`Filter ${label.toLowerCase()}…`}
          onChange={(event) => { setFilter(event.target.value); load(event.target.value, 1, 250); }} />
      </label>
    </div>
    {filtered && <div className="career-filter-notice">
      <span>Filtered · {data.matched_total} of {catalogTotal} {label.toLowerCase()}</span>
      <button type="button" disabled={busy} onClick={() => { setFilter(""); load("", 1, 0, data.unfiltered_total != null); }}>Show all</button>
    </div>}
    <div className="career-table-scroll" tabIndex={0} role="region" aria-label={`${label} table`}>
      <table><colgroup><col className="career-title-column" />{projects && <col className="career-experience-column" />}<col className="career-summary-column" /></colgroup><thead><tr><th scope="col">{projects ? "Project" : "Role / employer"}</th>{projects && <th scope="col">Experience</th>}<th scope="col">Summary</th></tr></thead>
        {data.items.map((row) => <tbody key={row.id} className={`career-record${"name" in row && row.skills.length ? " career-record-with-skills" : ""}`}>
          <tr>
            <td>{"name" in row ? <strong>{row.name}</strong> : <><strong>{row.title}</strong><span className="career-secondary">{row.company}</span></>}<Period record={row} /></td>
            {"name" in row && <td>{row.job ? <><span>{row.job.company}</span><span className="career-secondary">{row.job.title}</span></> : <span className="career-personal">Personal</span>}</td>}
            <td>{row.summary && <p className="career-row-summary">{row.summary}</p>}<KnowMore record={row} disabled={chatBusy || busy} onOpen={onOpen} /></td>
          </tr>
          {"name" in row && row.skills.length > 0 && <tr className="career-skills-row"><td colSpan={3}><Skills skills={row.skills} /></td></tr>}
        </tbody>)}
      </table>
    </div>
    {!data.items.length && <p className="career-empty">{data.total ? "No matches for this filter. Try another word." : "No matching records to display."}</p>}
    <div className="career-list-footer">
      <span role="status">{busy ? "Loading…" : `${start}–${end} of ${data.matched_total}${data.filter ? ` matching · ${data.total} total` : ""}`}</span>
      <nav aria-label={`${label} pagination`}><button type="button" disabled={busy || data.page <= 1} onClick={() => load(filter, data.page - 1)}>← Previous</button>
        <span>Page {data.page} of {pages}</span>
        <button type="button" disabled={busy || data.page >= pages} onClick={() => load(filter, data.page + 1)}>Next →</button></nav>
    </div>
    {error && <div className="career-list-error" role="alert">{error} <button type="button" onClick={() => load(query?.filter ?? filter, query?.page ?? 1, 0, query?.show_all)}>Try again</button></div>}
  </section>;
}

function Description({ title, text }: { title: string; text?: string }) {
  if (!text?.trim()) return null;
  return <details className="career-card-section" open={title === "Overview"}><summary><h4>{title}</h4></summary><div className="career-card-prose"><ChatAnswer text={text} /></div></details>;
}

function ProjectLink({ url, children }: { url?: string; children: string }) {
  if (!url) return null;
  try {
    if (!["http:", "https:"].includes(new URL(url).protocol)) return null;
  } catch { return null; }
  return <a href={url} target="_blank" rel="noopener noreferrer">{children} <span aria-hidden="true">↗</span></a>;
}

export function ProjectCard({ data }: { data: ProjectCardData }) {
  const project = data.record;
  return <section className="career-card" aria-label={`${project.name} project card`}>
    <header><span className="career-card-mark" aria-hidden="true">✳</span><div><span className="career-eyebrow">{project.kind === "personal" ? "PERSONAL PROJECT" : "PROFESSIONAL PROJECT"}</span><h3>{project.name}</h3><Period record={project} /></div></header>
    <div className="career-card-context">{project.job && <p><span>Experience</span><strong>{project.job.title} · {project.job.company}</strong></p>}{project.role && <p><span>My role</span><strong>{project.role}</strong></p>}</div>
    <Skills skills={project.skills} />
    <div className="career-card-links"><ProjectLink url={project.website_url}>Website</ProjectLink><ProjectLink url={project.repository_url}>Repository</ProjectLink></div>
    <Description title="Overview" text={project.summary} />
    <Description title="About the project" text={project.description} />
    <Description title="My contribution" text={project.contribution} />
    <Description title="Outcomes" text={project.outcomes} />
  </section>;
}

export function JobCard({ data }: { data: JobCardData }) {
  const job = data.record;
  return <section className="career-card" aria-label={`${job.title} job card`}>
    <header><span className="career-card-mark" aria-hidden="true">✳</span><div><span className="career-eyebrow">PROFESSIONAL EXPERIENCE</span><h3>{job.title}</h3><p className="career-company">{job.company}{job.location && ` · ${job.location}`}</p><Period record={job} /></div></header>
    <Description title="Overview" text={job.summary} />
    <Description title="Responsibilities" text={job.responsibilities} />
    <Description title="Achievements" text={job.achievements} />
  </section>;
}

function downloadFilename(response: Response, fallback: string) {
  const encoded = /(?:^|;)\s*filename\*=UTF-8''([^;]+)/i.exec(response.headers.get("content-disposition") ?? "")?.[1];
  if (!encoded) return fallback;
  try {
    const filename = decodeURIComponent(encoded.trim());
    if (filename.trim() && filename.length <= 255 && !/[\\/]/.test(filename)
      && ![...filename].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return filename;
  } catch { /* Keep the verified card filename when a header is malformed. */ }
  return fallback;
}

function ResumeDownload({ data }: { data: ResumeDownloadData }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const active = useRef<AbortController | null>(null);
  const errorId = useId();
  useEffect(() => () => { active.current?.abort(); active.current = null; }, []);

  async function download() {
    if (active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setDownloading(true);
    setError("");
    try {
      const response = await fetch(`/api/resumes/download?token=${encodeURIComponent(data.token)}`, {
        cache: "no-store", signal: controller.signal,
      });
      if (response.status === 404 || response.status === 410) {
        setUnavailable(true);
        throw new Error("This resume is no longer available. Please ask for an updated resume.");
      }
      if (!response.ok || response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/pdf")
        throw new Error("The download could not be started. Please try again.");
      const file = await response.blob();
      if (!file.size) throw new Error("The download could not be started. Please try again.");
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = downloadFilename(response, data.filename);
      link.hidden = true;
      document.body.append(link);
      link.click();
      setTimeout(() => { link.remove(); URL.revokeObjectURL(url); }, 1000);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error && failure.name !== "TypeError"
        ? failure.message : "The download could not be started. Please try again.");
    } finally {
      if (active.current === controller) {
        active.current = null;
        setDownloading(false);
      }
    }
  }

  const size = data.size >= 1024 * 1024
    ? `${(data.size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.ceil(data.size / 1024))} KB`;
  return <section className="resume-download" aria-label={`${data.title} resume download`}>
    <div className="resume-download-summary">
      <span className="resume-document-icon" aria-hidden="true">
        <svg width="27" height="32" viewBox="0 0 27 32" fill="none"><path d="M16 2H5a2 2 0 0 0-2 2v24a2 2 0 0 0 2 2h17a2 2 0 0 0 2-2V10L16 2Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /><path d="M16 2v8h8M8 17h11M8 22h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </span>
      <div className="resume-download-copy"><span className="career-eyebrow">TAKE A CLOSER LOOK</span><h3>{data.title}</h3><p>PDF <span aria-hidden="true">·</span> {size}</p></div>
    </div>
    <button type="button" className="resume-download-button" disabled={downloading || unavailable}
      aria-busy={downloading} aria-describedby={error ? errorId : undefined} onClick={() => void download()}>
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 2v10m-4-4 4 4 4-4M3 13v4h14v-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      {downloading ? "Downloading…" : unavailable ? "Resume unavailable" : "Download Resume"}
    </button>
    {error && <p id={errorId} className="resume-download-error" role="alert">{error}</p>}
  </section>;
}

export function ChatComponentView(props: ViewProps) {
  if (props.data.type === "resume_download") return <ResumeDownload data={props.data} />;
  if (props.data.type === "project_card") return <ProjectCard data={props.data} />;
  if (props.data.type === "job_card") return <JobCard data={props.data} />;
  return <CareerList {...props} data={props.data} />;
}
