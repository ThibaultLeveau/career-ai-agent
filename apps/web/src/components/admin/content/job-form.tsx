"use client";

import Link from "next/link";
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

export function JobForm({
  job,
  projects = [],
}: {
  job?: Job;
  projects?: Project[];
}) {
  const editor = useEditor<JobInput>(
    {
      title: job?.title ?? "",
      company: job?.company ?? "",
      location: job?.location ?? "",
      start_month: job?.start_month ?? null,
      end_month: job?.end_month ?? null,
      ongoing: job?.ongoing ?? false,
      summary: job?.summary ?? "",
      responsibilities: job?.responsibilities ?? "",
      achievements: job?.achievements ?? "",
    },
    "jobs",
    job?.id,
  );
  const { values, setValues } = editor;
  const field = (
    name:
      | "title"
      | "company"
      | "location"
      | "summary"
      | "responsibilities"
      | "achievements",
  ) => ({
    value: values[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues({ ...values, [name]: e.target.value }),
  });
  return (
    <>
      <form onSubmit={editor.submit}>
        <fieldset
          disabled={editor.busy}
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
          <Field label="Summary" multiline {...field("summary")} />
          <Field
            label="Responsibilities"
            multiline
            {...field("responsibilities")}
          />
          <Field label="Achievements" multiline {...field("achievements")} />
        </fieldset>
        <Notice error>{editor.error}</Notice>
        <Notice>{editor.message}</Notice>
        <SaveBar
          busy={editor.busy}
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
                <span>{project.summary || project.role}</span>
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
