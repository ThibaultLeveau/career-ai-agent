"use client";

import { RecordRow } from "./record-row";
import Link from "next/link";
import { useState } from "react";
import {
  fileSize,
  period,
  type Job,
  type Project,
  type ResumeDocument,
} from "@/lib/content";
import { Empty, ListToolbar } from "./shared";

export function JobsList({ jobs }: { jobs: Job[] }) {
  const [query, setQuery] = useState("");
  const filtered = jobs.filter((job) =>
    `${job.title} ${job.company} ${job.location}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      <ListToolbar
        query={query}
        setQuery={setQuery}
        label="Jobs"
        href="/admin/jobs/new"
      />
      <div className="content-list">
        {filtered.map((job) => (
          <RecordRow
            key={job.id}
            collection="jobs"
            recordId={job.id}
            label={job.title}
            initial={job.ingestion}
          >
            <Link className="record-link" href={`/admin/jobs/${job.id}`}>
              <strong>{job.title}</strong>
              <span>
                {job.company}
                {job.location && ` · ${job.location}`}
              </span>
            </Link>
            <span className="record-meta">
              {period(job)}
              <small>
                {job.project_count}{" "}
                {job.project_count === 1 ? "project" : "projects"}
              </small>
            </span>
          </RecordRow>
        ))}
        {!filtered.length && (
          <Empty>
            {jobs.length
              ? "No matching jobs."
              : "No jobs yet. Add your first experience."}
          </Empty>
        )}
      </div>
    </>
  );
}

export function ProjectsList({
  projects,
  jobs,
}: {
  projects: Project[];
  jobs: Job[];
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [jobId, setJobId] = useState("");
  const company = (id: number | null) =>
    jobs.find((job) => job.id === id)?.company;
  const filtered = projects.filter(
    (project) =>
      (!kind || project.kind === kind) &&
      (!jobId || project.job_id === Number(jobId)) &&
      `${project.name} ${project.summary} ${company(project.job_id) ?? ""} ${project.skills.map((skill) => skill.keyword).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <>
      <ListToolbar
        query={query}
        setQuery={setQuery}
        label="Projects"
        href="/admin/projects/new"
      >
        <select
          aria-label="Project type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">All types</option>
          <option value="professional">Professional</option>
          <option value="personal">Personal</option>
        </select>
        <select
          aria-label="Filter by job"
          value={jobId}
          onChange={(e) => setJobId(e.target.value)}
        >
          <option value="">All jobs</option>
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              {job.title} · {job.company}
            </option>
          ))}
        </select>
      </ListToolbar>
      <div className="content-list">
        {filtered.map((project) => (
          <RecordRow
            key={project.id}
            collection="projects"
            recordId={project.id}
            label={project.name}
            initial={project.ingestion}
          >
            <Link
              className="record-link"
              href={`/admin/projects/${project.id}`}
            >
              <strong>{project.name}</strong>
              <span>
                {company(project.job_id) ?? "Personal project"}
                {project.role && ` · ${project.role}`}
              </span>
              <span className="skill-tags">
                {project.skills.map((skill) => (
                  <span className="pill" key={skill.id}>
                    {skill.keyword}
                  </span>
                ))}
              </span>
            </Link>
            <span className="record-meta">
              <span className="pill muted-pill">
                {project.kind === "professional" ? "Professional" : "Personal"}
              </span>
              <small>{period(project)}</small>
            </span>
          </RecordRow>
        ))}
        {!filtered.length && (
          <Empty>
            {projects.length
              ? "No matching projects."
              : "No projects yet. Add something you built."}
          </Empty>
        )}
      </div>
    </>
  );
}

export function DocumentsList({ documents }: { documents: ResumeDocument[] }) {
  const [query, setQuery] = useState("");
  const filtered = documents.filter((doc) =>
    `${doc.title} ${doc.filename}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <ListToolbar
        query={query}
        setQuery={setQuery}
        label="Documents"
        href="/admin/documents/new"
      />
      <div className="content-list">
        {filtered.map((doc) => (
          <RecordRow
            key={doc.id}
            collection="documents"
            recordId={doc.id}
            label={doc.title}
            initial={doc.ingestion}
          >
            <Link className="record-link" href={`/admin/documents/${doc.id}`}>
              <strong>{doc.title}</strong>
              <span>{doc.filename}</span>
            </Link>
            <span className="record-meta">
              {fileSize(doc.size)}
              <small>{doc.created_at.slice(0, 10)}</small>
            </span>
          </RecordRow>
        ))}
        {!filtered.length && (
          <Empty>
            {documents.length
              ? "No matching documents."
              : "No documents yet. Upload your first resume PDF."}
          </Empty>
        )}
      </div>
    </>
  );
}
