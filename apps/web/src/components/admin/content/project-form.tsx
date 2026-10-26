"use client";

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
  const editor = useEditor<ProjectInput>(
    {
      name: project?.name ?? "",
      role: project?.role ?? "",
      start_month: project?.start_month ?? null,
      end_month: project?.end_month ?? null,
      ongoing: project?.ongoing ?? false,
      summary: project?.summary ?? "",
      description: project?.description ?? "",
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
  const field = (
    name:
      | "name"
      | "role"
      | "summary"
      | "description"
      | "outcomes"
      | "website_url"
      | "repository_url",
  ) => ({
    value: values[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues({ ...values, [name]: e.target.value }),
  });
  return (
    <>
      <form onSubmit={editor.submit}>
        <fieldset
          disabled={editor.busy || creatingSkill}
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
          <Field label="Summary" multiline {...field("summary")} />
          <Field label="Description" multiline {...field("description")} />
          <Field label="Outcomes" multiline {...field("outcomes")} />
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
          busy={editor.busy || creatingSkill}
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
