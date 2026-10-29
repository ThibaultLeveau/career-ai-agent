export type DetailAction = { type: "show_project" | "show_job"; token: string };
export type ComponentReference = { type: "project" | "job"; id: number; label: string };
type Timeline = {
  id: number;
  start_month: string | null;
  end_month: string | null;
  ongoing: boolean;
  summary: string;
  action: DetailAction;
};
export type ProjectRow = Timeline & {
  name: string;
  role: string;
  kind: "personal" | "professional";
  job: { id: number; title: string; company: string } | null;
  skills: string[];
};
export type JobRow = Timeline & { title: string; company: string; location: string };
type ListPage = {
  token: string;
  total: number;
  matched_total: number;
  page: number;
  page_size: number;
  filter: string;
  filtered?: boolean;
  unfiltered_total?: number | null;
  scope_label?: string;
};
export type ProjectListData = ListPage & { type: "project_list"; items: ProjectRow[] };
export type JobListData = ListPage & { type: "job_list"; items: JobRow[] };
export type CareerListData = ProjectListData | JobListData;
export type ProjectCardData = {
  type: "project_card";
  record: ProjectRow & { description: string; outcomes: string; contribution?: string; website_url?: string; repository_url?: string };
};
export type JobCardData = {
  type: "job_card";
  record: JobRow & { responsibilities: string; achievements: string };
};
export type ChatComponent = CareerListData | ProjectCardData | JobCardData;
export type ComponentEvent = { introduction: string; component: ChatComponent };
export type ChatBlock = { type: "text"; text: string } | ({ type: "component" } & ComponentEvent);

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
function text(value: unknown, max: number, min = 0): value is string {
  return typeof value === "string" && value.length >= min && value.length <= max;
}
function integer(value: unknown, min: number, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
}
function month(value: unknown): boolean {
  return value === null || (typeof value === "string" && /^[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(value));
}
function timeline(value: unknown): value is Record<string, unknown> {
  return object(value) && integer(value.id, 1) && month(value.start_month) && month(value.end_month)
    && typeof value.ongoing === "boolean" && text(value.summary, 8000)
    && object(value.action) && text(value.action.token, 2048, 1);
}
function project(value: unknown): value is ProjectRow {
  return timeline(value) && text(value.name, 200, 1) && text(value.role, 200)
    && ["personal", "professional"].includes(String(value.kind))
    && object(value.action) && value.action.type === "show_project"
    && Array.isArray(value.skills) && value.skills.length <= 500 && value.skills.every((skill) => text(skill, 100, 1))
    && (value.job === null || (object(value.job) && integer(value.job.id, 1)
      && text(value.job.title, 200, 1) && text(value.job.company, 200, 1)));
}
function job(value: unknown): value is JobRow {
  return timeline(value) && text(value.title, 200, 1) && text(value.company, 200, 1)
    && text(value.location, 200) && object(value.action) && value.action.type === "show_job";
}

export function isChatComponent(value: unknown): value is ChatComponent {
  if (!object(value)) return false;
  if (value.type === "project_card") return object(value.record)
    && text(value.record.description, 8000) && text(value.record.outcomes, 8000)
    && (value.record.contribution === undefined || text(value.record.contribution, 8000))
    && (value.record.website_url === undefined || text(value.record.website_url, 2048))
    && (value.record.repository_url === undefined || text(value.record.repository_url, 2048))
    && project(value.record);
  if (value.type === "job_card") return object(value.record)
    && text(value.record.responsibilities, 8000) && text(value.record.achievements, 8000) && job(value.record);
  if (value.type !== "project_list" && value.type !== "job_list") return false;
  return text(value.token, 240000, 1) && integer(value.total, 0, 10000)
    && (value.filtered === undefined || typeof value.filtered === "boolean")
    && (value.unfiltered_total === undefined || value.unfiltered_total === null || integer(value.unfiltered_total, 0))
    && (value.scope_label === undefined || text(value.scope_label, 200))
    && integer(value.matched_total, 0, value.total as number) && integer(value.page_size, 1, 20)
    && integer(value.page, 1, Math.max(1, Math.ceil((value.matched_total as number) / (value.page_size as number))))
    && text(value.filter, 200) && Array.isArray(value.items) && value.items.length <= (value.page_size as number)
    && value.items.every(value.type === "project_list" ? project : job);
}

export function isComponentEvent(value: unknown): value is ComponentEvent {
  return object(value) && text(value.introduction, 1600, 1) && value.introduction.trim().length > 0
    && isChatComponent(value.component);
}

export function componentReferences(component: ChatComponent): ComponentReference[] {
  const rows = "items" in component ? component.items : [component.record];
  return rows.map((row) => "name" in row
    ? { type: "project", id: row.id, label: row.name }
    : { type: "job", id: row.id, label: `${row.title} — ${row.company}` });
}
