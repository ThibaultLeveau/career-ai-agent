"use client";

import { useEffect, useRef, useTransition } from "react";
import { useRouter } from "next/navigation";
import { catalogHref, type CareerCollection, type CareerFacets } from "@/lib/public-career";

export function ExperienceFilters({ collection, facets, query }: {
  collection: CareerCollection;
  facets: CareerFacets;
  query: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const params = new URLSearchParams(query);
  const draft = useRef(query);
  const requests = useRef(new Set<string>());
  const hasFilters = [...params.keys()].some((key) => key !== "page");

  function signature(value: string) {
    const sorted = new URLSearchParams(value);
    sorted.sort();
    return sorted.toString();
  }

  useEffect(() => {
    const committed = signature(query);
    const ownNavigation = requests.current.has(committed);
    if (ownNavigation) {
      requests.current.delete(committed);
      // A completed navigation must not replace a newer draft still being typed.
      if (signature(draft.current) !== committed) return;
    } else if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    requests.current.clear();
    draft.current = query;
    const values = new URLSearchParams(query);
    for (const field of Array.from(form.current?.elements ?? [])) {
      if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement)) continue;
      const value = values.get(field.name) ?? "";
      if (ownNavigation && field === document.activeElement && field.name === "q" && field.value.trim() === value) continue;
      if (field.value !== value) field.value = value;
    }
  }, [query]);

  useEffect(() => {
    const restoreHistory = () => {
      requests.current.clear();
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
    window.addEventListener("popstate", restoreHistory);
    return () => {
      if (timer.current) clearTimeout(timer.current);
      window.removeEventListener("popstate", restoreHistory);
    };
  }, []);

  function update(name: string, value: string, delay = 0) {
    if (timer.current) clearTimeout(timer.current);
    const next = new URLSearchParams(draft.current);
    if (value) next.set(name, value); else next.delete(name);
    if (name !== "q" && search.current) {
      const q = search.current.value.trim();
      if (q) next.set("q", q); else next.delete("q");
    }
    next.delete("page");
    draft.current = next.toString();
    const navigate = () => {
      timer.current = null;
      requests.current.add(signature(next.toString()));
      startTransition(() => router.push(catalogHref(collection, next), { scroll: false }));
    };
    if (delay) timer.current = setTimeout(navigate, delay); else navigate();
  }

  function select(label: string, name: string, empty: string, options: { value: string; label: string }[]) {
    return <label className="experience-filter-select">
      <span>{label}</span>
      <select name={name} aria-label={label} defaultValue={params.get(name) ?? ""} onChange={(event) => update(name, event.target.value)}>
        <option value="">{empty}</option>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>;
  }

  return <form ref={form} className="experience-filters" role="search" aria-label={`Filter ${collection}`} aria-busy={pending}
    action={`/${collection}`} onSubmit={(event) => { event.preventDefault(); update("q", search.current?.value.trim() ?? ""); }}>
    <label className="experience-filter-search">
      <span className="sr-only">Search {collection}</span>
      <svg viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5" /><path d="m13 13 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
      <input ref={search} type="search" name="q" maxLength={200} defaultValue={params.get("q") ?? ""}
        placeholder={collection === "jobs" ? "Search roles, companies, skills…" : "Search projects, skills, ideas…"}
        onChange={(event) => update("q", event.target.value.trim(), 300)} />
    </label>
    <div className="experience-filter-options">
      {collection === "jobs"
        ? select("Company", "company", "All companies", facets.companies.map((company) => ({ value: company, label: company })))
        : <>{select("Type", "kind", "All types", [{ value: "professional", label: "Professional" }, { value: "personal", label: "Personal" }])}
          {select("Experience", "job_id", "All experiences", facets.jobs.map((job) => ({ value: String(job.id), label: `${job.company} · ${job.title}` })))}</>}
      {select("Skill", "skill_id", "All skills", facets.skills.map((skill) => ({ value: String(skill.id), label: skill.keyword })))}
      {select("Status", "status", "All statuses", [{ value: "ongoing", label: "Ongoing" }, { value: "past", label: "Past" }])}
      {hasFilters && <button className="experience-filter-clear" type="button" onClick={() => {
        if (timer.current) clearTimeout(timer.current);
        timer.current = null;
        draft.current = "";
        requests.current.add("");
        for (const field of Array.from(form.current?.elements ?? [])) {
          if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) field.value = "";
        }
        startTransition(() => router.push(`/${collection}`, { scroll: false }));
      }}>Clear filters <span aria-hidden="true">×</span></button>}
    </div>
    <span className="sr-only" role="status">{pending ? `Updating ${collection}…` : ""}</span>
  </form>;
}
