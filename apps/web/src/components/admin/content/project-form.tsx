"use client";

import { IngestionStatus } from "../ingestion-status";

import { useState } from "react";
import type { Job, Project, ProjectInput, Skill } from "@/lib/content";
import { Notice } from "../ui";
import {
  DeleteButton,
  Field,
  SaveBar,
  TimelineFields,
  useEditor,
} from "./shared";
import { SkillPicker } from "./skill-picker";
import { MARKDOWN_LIMIT, SMALL_SUMMARY_LIMIT, MarkdownField, characterCount } from "./markdown-field";
import { SmallSummaryField } from "./small-summary-field";

export function ProjectForm({
  project,
  jobs,
  skills,
  jobId,
}: {
  project?: Project;
  jobs: Job[];
  skills: Skill[];
  jobId?: number;
}) {
  const [creatingSkill, setCreatingSkill] = useState(false);
  const [generating, setGenerating] = useState(false);
  const editor = useEditor<ProjectInput>(
    {
      name: project?.name ?? "",
      role: project?.role ?? "",
      start_month: project?.start_month ?? null,
      end_month: project?.end_month ?? null,
      ongoing: project?.ongoing ?? false,
      summary: project?.summary ?? "",
      small_summary: project?.small_summary ?? "",
      description: project?.description ?? "",
      contribution: project?.contribution ?? "",
      outcomes: project?.outcomes ?? "",
      website_url: project?.website_url ?? "",
      repository_url: project?.repository_url ?? "",
      job_id: project ? project.job_id : (jobId ?? null),
      skill_ids: project?.skills.map((skill) => skill.id) ?? [],
    },
    "projects",
    project?.id,
  );
  const { values, setValues } = editor;
  const busy = editor.busy || creatingSkill || generating;
  const invalid = [values.summary, values.description, values.contribution, values.outcomes].some((value) => characterCount(value) > MARKDOWN_LIMIT) || characterCount(values.small_summary) > SMALL_SUMMARY_LIMIT;
  const field = (
    name:
      | "name"
      | "role"
      | "website_url"
      | "repository_url",
  ) => ({
    value: values[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues((current) => ({ ...current, [name]: e.target.value })),
  });
  return (
    <>
      {project && (
        <IngestionStatus
          sourceType="projects"
          recordId={project.id}
          initial={project.ingestion}
        />
      )}
      <form onSubmit={(event) => { if (creatingSkill || generating) event.preventDefault(); else void editor.submit(event); }}>
        <fieldset
          disabled={busy}
          className="settings-section content-form"
        >
          <div className="field-grid">
            <Field label="Project name" required {...field("name")} />
            <Field label="Your role" {...field("role")} />
          </div>
          <label>
            Job
            <select
              aria-label="Job"
              value={values.job_id ?? ""}
              onChange={(e) =>
                setValues({
                  ...values,
                  job_id: e.target.value ? Number(e.target.value) : null,
                })
              }
            >
              <option value="">None — personal project</option>
              {jobs.map((job) => (
                <option value={job.id} key={job.id}>
                  {job.title} · {job.company}
                </option>
              ))}
            </select>
            <small>
              {values.job_id ? "Professional project" : "Personal project"}
            </small>
          </label>
          <TimelineFields
            value={values}
            onChange={(change) => setValues({ ...values, ...change })}
          />
          <MarkdownField key={`overview-${editor.resetVersion}`} label="Overview" value={values.summary} disabled={busy} onChange={(summary) => setValues((current) => ({ ...current, summary }))} />
          <SmallSummaryField key={`small-summary-${editor.resetVersion}`} value={values.small_summary} overview={values.summary} disabled={busy} onBusyChange={setGenerating} onChange={(small_summary) => setValues((current) => ({ ...current, small_summary }))} />
          <MarkdownField key={`description-${editor.resetVersion}`} label="Description" value={values.description} disabled={busy} onChange={(description) => setValues((current) => ({ ...current, description }))} />
          <MarkdownField key={`contribution-${editor.resetVersion}`} label="My contribution" value={values.contribution} disabled={busy} onChange={(contribution) => setValues((current) => ({ ...current, contribution }))} />
          <MarkdownField key={`outcomes-${editor.resetVersion}`} label="Outcomes" value={values.outcomes} disabled={busy} onChange={(outcomes) => setValues((current) => ({ ...current, outcomes }))} />
          <div className="field-grid">
            <Field
              label="Website URL"
              type="url"
              maxLength={2048}
              {...field("website_url")}
            />
            <Field
              label="Repository URL"
              type="url"
              maxLength={2048}
              {...field("repository_url")}
            />
          </div>
          <SkillPicker
            onBusyChange={setCreatingSkill}
            skills={skills}
            selected={values.skill_ids}
            onChange={(skill_ids) => setValues({ ...values, skill_ids })}
          />
        </fieldset>
        <Notice error>{editor.error}</Notice>
        <Notice>{editor.message}</Notice>
        <SaveBar
          busy={busy}
          saving={editor.busy}
          invalid={invalid}
          dirty={editor.dirty}
          isNew={!project}
          reset={editor.reset}
        />
      </form>
      {project && (
        <div className="record-footer">
          <DeleteButton
            path={`projects/${project.id}`}
            label={project.name}
            returnTo="/admin/projects"
          />
        </div>
      )}
    </>
  );
}
