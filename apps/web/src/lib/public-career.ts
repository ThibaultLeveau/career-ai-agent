export type PublicSkill = { id: number; keyword: string };
export type LinkedJob = { id: number; title: string; company: string };
export type PublicTimeline = {
  id: number;
  start_month: string | null;
  end_month: string | null;
  ongoing: boolean;
  summary: string;
};
export type PublicJob = PublicTimeline & {
  title: string;
  company: string;
  location: string;
  skills: PublicSkill[];
  project_count: number;
};
export type PublicProject = PublicTimeline & {
  name: string;
  role: string;
  kind: "personal" | "professional";
  job: LinkedJob | null;
  skills: PublicSkill[];
};
export type PublicJobDetail = PublicJob & {
  responsibilities: string;
  achievements: string;
  projects: PublicProject[];
};
export type PublicProjectDetail = PublicProject & {
  description: string;
  contribution: string;
  outcomes: string;
  website_url: string;
  repository_url: string;
};
export type CareerFacets = {
  companies: string[];
  skills: PublicSkill[];
  jobs: LinkedJob[];
};
export type CareerPage<T> = {
  items: T[];
  total: number;
  matched_total: number;
  page: number;
  page_size: number;
  facets: CareerFacets;
};
export type CareerCollection = "jobs" | "projects";
export type CareerSearchParams = Record<string, string | string[] | undefined>;

export function catalogParams(collection: CareerCollection, input: CareerSearchParams) {
  const params = new URLSearchParams();
  const value = (name: string) => {
    const entry = input[name];
    return Array.isArray(entry) ? entry[0] ?? "" : entry ?? "";
  };
  const q = value("q").trim().slice(0, 200);
  if (q) params.set("q", q);
  const status = value("status");
  if (status === "ongoing" || status === "past") params.set("status", status);
  const skill = value("skill_id");
  if (/^[1-9]\d*$/.test(skill) && Number.isSafeInteger(Number(skill))) params.set("skill_id", skill);
  if (collection === "jobs") {
    const company = value("company").slice(0, 200);
    if (company) params.set("company", company);
  } else {
    const kind = value("kind");
    if (kind === "personal" || kind === "professional") params.set("kind", kind);
    const job = value("job_id");
    if (/^[1-9]\d*$/.test(job) && Number.isSafeInteger(Number(job))) params.set("job_id", job);
  }
  const page = Number(value("page"));
  if (Number.isSafeInteger(page) && page > 1 && page <= 1_000_000) params.set("page", String(page));
  return params;
}

export function catalogHref(collection: CareerCollection, params: URLSearchParams) {
  const sorted = new URLSearchParams(params);
  sorted.sort();
  const query = sorted.toString();
  return `/${collection}${query ? `?${query}` : ""}`;
}

export function returnHref(collection: CareerCollection, input: string | string[] | undefined) {
  const from = Array.isArray(input) ? input[0] : input;
  if (!from || !from.startsWith(`/${collection}?`)) return `/${collection}`;
  try {
    const url = new URL(from, "https://portfolio.invalid");
    if (url.origin !== "https://portfolio.invalid" || url.pathname !== `/${collection}`) return `/${collection}`;
    return catalogHref(collection, catalogParams(collection, Object.fromEntries(url.searchParams)));
  } catch {
    return `/${collection}`;
  }
}

export function experiencePeriod(record: PublicTimeline) {
  const month = (value: string | null) => value
    ? new Intl.DateTimeFormat("en", { month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}-01T00:00:00Z`))
    : "";
  const start = month(record.start_month);
  const end = record.ongoing ? "Present" : month(record.end_month);
  if (!start && !end) return "Dates not recorded";
  if (!start) return record.ongoing ? "Ongoing" : `Until ${end}`;
  return end ? `${start} — ${end}` : start;
}

export function monogram(label: string) {
  return label.trim().split(/\s+/).slice(0, 2).map((word) => Array.from(word)[0]).join("").toUpperCase();
}
