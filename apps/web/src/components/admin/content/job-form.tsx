"use client";

import { IngestionStatus } from "../ingestion-status";

import Link from "next/link";
import { useState } from "react";
import type { Job, JobInput, Project } from "@/lib/content";
import { Notice } from "../ui";
import {
  DeleteButton,
  Empty,
  Field,
  SaveBar,
  TimelineFields,
  useEditor,
} from "./shared";
import { MARKDOWN_LIMIT, SMALL_SUMMARY_LIMIT, MarkdownField, characterCount } from "./markdown-field";
import { SmallSummaryField } from "./small-summary-field";

export function JobForm({
  job,
  projects = [],
}: {
  job?: Job;
  projects?: Project[];
}) {
  const [generating, setGenerating] = useState(false);
  const editor = useEditor<JobInput>(
    {
      title: job?.title ?? "",
      company: job?.company ?? "",
      location: job?.location ?? "",
      start_month: job?.start_month ?? null,
      end_month: job?.end_month ?? null,
      ongoing: job?.ongoing ?? false,
      summary: job?.summary ?? "",
      small_summary: job?.small_summary ?? "",
      responsibilities: job?.responsibilities ?? "",
      achievements: job?.achievements ?? "",
    },
    "jobs",
    job?.id,
  );
  const { values, setValues } = editor;
  const busy = editor.busy || generating;
  const invalid = [values.summary, values.responsibilities, values.achievements].some((value) => characterCount(value) > MARKDOWN_LIMIT) || characterCount(values.small_summary) > SMALL_SUMMARY_LIMIT;
  const field = (
    name:
      | "title"
      | "company"
      | "location",
  ) => ({
    value: values[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues((current) => ({ ...current, [name]: e.target.value })),
  });
  return (
    <>
      {job && (
        <IngestionStatus
          sourceType="jobs"
          recordId={job.id}
          initial={job.ingestion}
        />
      )}
      <form onSubmit={(event) => { if (generating) event.preventDefault(); else void editor.submit(event); }}>
        <fieldset
          disabled={busy}
          className="settings-section content-form"
        >
          <div className="field-grid">
            <Field label="Role / title" required {...field("title")} />
            <Field label="Company" required {...field("company")} />
          </div>
          <Field label="Location" {...field("location")} />
          <TimelineFields
            value={values}
            onChange={(change) => setValues({ ...values, ...change })}
          />
          <MarkdownField key={`overview-${editor.resetVersion}`} label="Overview" value={values.summary} disabled={busy} onChange={(summary) => setValues((current) => ({ ...current, summary }))} />
          <SmallSummaryField key={`small-summary-${editor.resetVersion}`} value={values.small_summary} overview={values.summary} disabled={busy} onBusyChange={setGenerating} onChange={(small_summary) => setValues((current) => ({ ...current, small_summary }))} />
          <MarkdownField key={`responsibilities-${editor.resetVersion}`} label="Responsibilities" value={values.responsibilities} disabled={busy} onChange={(responsibilities) => setValues((current) => ({ ...current, responsibilities }))} />
          <MarkdownField key={`achievements-${editor.resetVersion}`} label="Achievements" value={values.achievements} disabled={busy} onChange={(achievements) => setValues((current) => ({ ...current, achievements }))} />
        </fieldset>
        <Notice error>{editor.error}</Notice>
        <Notice>{editor.message}</Notice>
        <SaveBar
          busy={busy}
          saving={editor.busy}
          invalid={invalid}
          dirty={editor.dirty}
          isNew={!job}
          reset={editor.reset}
        />
      </form>
      {job && (
        <section className="related-section">
          <div className="related-heading">
            <h2>Projects</h2>
            <Link
              href={`/admin/projects/new?job=${job.id}`}
              className="button button-small"
            >
              Add project
            </Link>
          </div>
          <div className="content-list">
            {projects.map((project) => (
              <Link
                className="content-row record-link"
                href={`/admin/projects/${project.id}`}
                key={project.id}
              >
                <strong>{project.name}</strong>
                <span>{project.small_summary || project.role}</span>
              </Link>
            ))}
            {!projects.length && <Empty>No projects linked to this job.</Empty>}
          </div>
          <div className="record-footer">
            <DeleteButton
              path={`jobs/${job.id}`}
              label={job.title}
              returnTo="/admin/jobs"
            />
          </div>
        </section>
      )}
    </>
  );
}
