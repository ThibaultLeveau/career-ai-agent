import type { IngestionSummary } from "./ingestion";

export type ContentRecord = {
  id: number;
  created_at: string;
  updated_at: string;
  ingestion: IngestionSummary;
};
export type Timeline = {
  start_month: string | null;
  end_month: string | null;
  ongoing: boolean;
  summary: string;
};
export type JobInput = Timeline & {
  title: string;
  company: string;
  location: string;
  responsibilities: string;
  achievements: string;
};
export type Job = JobInput & ContentRecord & { project_count: number };
export type Skill = ContentRecord & { keyword: string };
export type ProjectInput = Timeline & {
  name: string;
  role: string;
  description: string;
  outcomes: string;
  website_url: string;
  repository_url: string;
  job_id: number | null;
  skill_ids: number[];
};
export type Project = Omit<ProjectInput, "skill_ids"> &
  ContentRecord & {
    kind: "professional" | "personal";
    skills: Skill[];
  };
export type ResumeDocument = ContentRecord & {
  title: string;
  filename: string;
  size: number;
};
export function period(record: Timeline) {
  return (
    [record.start_month, record.ongoing ? "Present" : record.end_month]
      .filter(Boolean)
      .join(" — ") || "Dates not set"
  );
}
export function fileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.ceil(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
