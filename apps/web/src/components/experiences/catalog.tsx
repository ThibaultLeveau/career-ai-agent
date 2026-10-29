import Link from "next/link";
import { ExperienceFilters } from "./filters";
import { JobExperienceCard, ProjectExperienceCard } from "./cards";
import { catalogHref, catalogParams, type CareerCollection, type CareerPage, type CareerSearchParams, type PublicJob, type PublicProject } from "@/lib/public-career";
import { publicCareerData } from "@/lib/public-career-server";

export async function ExperienceCatalog({ collection, searchParams }: { collection: CareerCollection; searchParams: CareerSearchParams }) {
  const params = catalogParams(collection, searchParams);
  const data = await publicCareerData<CareerPage<PublicJob | PublicProject>>(`${collection}?${params}`);
  if (data.page > 1) params.set("page", String(data.page)); else params.delete("page");
  const from = catalogHref(collection, params);
  const jobs = collection === "jobs";
  const title = jobs ? "Jobs" : "Projects";
  const filtered = [...params.keys()].some((key) => key !== "page");
  const pages = Math.max(1, Math.ceil(data.matched_total / data.page_size));
  const start = data.items.length ? (data.page - 1) * data.page_size + 1 : 0;
  const end = start ? start + data.items.length - 1 : 0;
  const pageLink = (page: number) => {
    const next = new URLSearchParams(params);
    if (page > 1) next.set("page", String(page)); else next.delete("page");
    return catalogHref(collection, next);
  };
  return <>
    <header className="experience-hero">
      <p className="experience-eyebrow">EXPERIENCES / {title.toUpperCase()}</p>
      <h1>{jobs ? "The roles behind the work." : "Ideas, built into something real."}</h1>
      <p className="experience-intro">{jobs ? "Explore the teams I’ve joined, the work I’ve owned, and what we accomplished along the way." : "A closer look at the projects I’ve worked on, the choices behind them, and what they made possible."}</p>
      <div className="experience-hero-meta"><span>{data.total} {jobs ? (data.total === 1 ? "role" : "roles") : (data.total === 1 ? "project" : "projects")}</span><span className="experience-hero-dot" aria-hidden="true">·</span><span>{jobs ? "A journey through my work" : "Professional & personal work"}</span></div>
    </header>
    <nav className="experience-collection-tabs" aria-label="Experience collections">
      <Link href="/jobs" aria-current={jobs ? "page" : undefined}>Jobs</Link>
      <Link href="/projects" aria-current={!jobs ? "page" : undefined}>Projects</Link>
    </nav>
    <ExperienceFilters collection={collection} facets={data.facets} query={params.toString()} />
    <section aria-label={`${title} results`}>
      <div className="experience-results-heading"><h2>{filtered ? "Matching" : "All"} {collection} <span>{data.matched_total}</span></h2><p>Most recent first</p></div>
      {data.items.length ? <div className={jobs ? "experience-job-list" : "experience-project-grid"}>
        {data.items.map((record) => "title" in record ? <JobExperienceCard key={record.id} job={record} from={from} /> : <ProjectExperienceCard key={record.id} project={record} from={from} />)}
      </div> : <div className="experience-empty"><span aria-hidden="true">✳</span><h3>{filtered ? `No ${collection} match these filters.` : `No ${collection} to explore yet.`}</h3><p>{filtered ? "Try another search or clear a filter to see more of my work." : "Check back soon for more of my experience."}</p>{filtered && <Link href={`/${collection}`}>Clear all filters <span aria-hidden="true">→</span></Link>}</div>}
      {data.matched_total > 0 && <nav className="experience-pagination" aria-label={`${title} pagination`}>
        <span role="status">{start}–{end} of {data.matched_total} {collection}</span>
        <div>{data.page > 1 ? <Link aria-label="Previous" href={pageLink(data.page - 1)}>← Previous</Link> : <span aria-disabled="true">← Previous</span>}<span>Page {data.page} of {pages}</span>{data.page < pages ? <Link aria-label="Next" href={pageLink(data.page + 1)}>Next →</Link> : <span aria-disabled="true">Next →</span>}</div>
      </nav>}
    </section>
    <div className="experience-chat-invitation"><span aria-hidden="true">✳</span><div><h2>Want to connect the dots?</h2><p>Ask me about the experience behind the work.</p></div><Link href="/">Let’s talk <span aria-hidden="true">↗</span></Link></div>
  </>;
}
