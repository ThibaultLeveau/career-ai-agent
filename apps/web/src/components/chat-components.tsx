"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChatAnswer } from "@/components/chat-answer";
import { isChatComponent, type CareerListData, type ChatComponent, type DetailAction, type JobCardData, type JobRow, type ProjectCardData, type ProjectRow } from "@/lib/chat-components";

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
  const [query, setQuery] = useState<{ filter: string; page: number; delay: number } | null>(null);
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
          body: JSON.stringify({ token: initial.token, filter: query.filter, page: query.page }),
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
  }, [query, initial.token, initial.type]);

  function load(value: string, page: number, delay = 0) {
    setError("");
    setBusy(true);
    setQuery({ filter: value, page, delay });
  }
  const projects = data.type === "project_list";
  const label = projects ? "Projects" : "Jobs";
  const start = data.matched_total ? (data.page - 1) * data.page_size + 1 : 0;
  const end = start ? start + data.items.length - 1 : 0;
  const pages = Math.max(1, Math.ceil(data.matched_total / data.page_size));
  return <section className="career-list" aria-label={`${label} list`} aria-busy={busy}>
    <div className="career-list-toolbar">
      <div><span className="career-eyebrow">EXPLORE MY WORK</span><h3>{label} <span>{data.total}</span></h3></div>
      <label htmlFor={filterId} className="career-filter"><span className="sr-only">Filter {label.toLowerCase()}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" width="16" height="16" fill="none"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" /><path d="m13 13 4 4" stroke="currentColor" /></svg>
        <input id={filterId} type="text" value={filter} maxLength={200} placeholder={`Filter ${label.toLowerCase()}…`}
          onChange={(event) => { setFilter(event.target.value); load(event.target.value, 1, 250); }} />
      </label>
    </div>
    <div className="career-table-scroll" tabIndex={0} role="region" aria-label={`${label} table`}>
      <table><thead><tr><th scope="col">{projects ? "Project" : "Role / employer"}</th><th scope="col">Period</th>{projects && <th scope="col">Experience</th>}<th scope="col">Summary</th></tr></thead>
        {data.items.map((row) => <tbody key={row.id} className={`career-record${"name" in row && row.skills.length ? " career-record-with-skills" : ""}`}>
          <tr>
            <td>{"name" in row ? <strong>{row.name}</strong> : <><strong>{row.title}</strong><span className="career-secondary">{row.company}</span></>}</td>
            <td><Period record={row} /></td>
            {"name" in row && <td>{row.job ? <><span>{row.job.company}</span><span className="career-secondary">{row.job.title}</span></> : <span className="career-personal">Personal</span>}</td>}
            <td><p className="career-row-summary">{row.summary || "Explore the details of this work."}</p><KnowMore record={row} disabled={chatBusy || busy} onOpen={onOpen} /></td>
          </tr>
          {"name" in row && row.skills.length > 0 && <tr className="career-skills-row"><td colSpan={4}><Skills skills={row.skills} /></td></tr>}
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
    {error && <div className="career-list-error" role="alert">{error} <button type="button" onClick={() => load(query?.filter ?? filter, query?.page ?? 1)}>Try again</button></div>}
  </section>;
}

function Description({ title, text }: { title: string; text: string }) {
  if (!text) return null;
  return <div className="career-card-section"><h4>{title}</h4><ChatAnswer text={text} /></div>;
}

export function ProjectCard({ data }: { data: ProjectCardData }) {
  const project = data.record;
  return <section className="career-card" aria-label={`${project.name} project card`}>
    <header><span className="career-card-mark" aria-hidden="true">✳</span><div><span className="career-eyebrow">{project.kind === "personal" ? "PERSONAL PROJECT" : "PROFESSIONAL PROJECT"}</span><h3>{project.name}</h3><Period record={project} /></div></header>
    <div className="career-card-context">{project.job && <p><span>Experience</span><strong>{project.job.title} · {project.job.company}</strong></p>}{project.role && <p><span>My role</span><strong>{project.role}</strong></p>}</div>
    <Skills skills={project.skills} />
    <Description title="Overview" text={project.summary} />
    <Description title="About the project" text={project.description} />
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

export function ChatComponentView(props: ViewProps) {
  if (props.data.type === "project_card") return <ProjectCard data={props.data} />;
  if (props.data.type === "job_card") return <JobCard data={props.data} />;
  return <CareerList {...props} data={props.data} />;
}
