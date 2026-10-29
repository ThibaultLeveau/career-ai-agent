import Link from "next/link";
import { ChatAnswer } from "@/components/chat-answer";
import { ExperienceSkills, ProjectExperienceCard } from "./cards";
import { experiencePeriod, monogram, type PublicJobDetail, type PublicProjectDetail } from "@/lib/public-career";

function Narrative({ title, text }: { title: string; text: string }) {
  if (!text?.trim()) return null;
  return <section className="experience-detail-section"><h2>{title}</h2><div className="experience-prose answer-content"><ChatAnswer text={text} /></div></section>;
}

function MetadataItem({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children) return null;
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}

function ExternalLink({ url, children }: { url: string; children: string }) {
  try {
    if (!["http:", "https:"].includes(new URL(url).protocol)) return null;
  } catch { return null; }
  return <a href={url} target="_blank" rel="noopener noreferrer">{children}<span aria-hidden="true">↗</span></a>;
}

function Breadcrumbs({ collection, title, back }: { collection: "jobs" | "projects"; title: string; back: string }) {
  return <nav className="experience-breadcrumbs" aria-label="Breadcrumb"><Link href={back} aria-label={`Back to ${collection}`}>← {collection === "jobs" ? "Jobs" : "Projects"}</Link><span aria-hidden="true">/</span><span aria-current="page">{title}</span></nav>;
}

function DetailInvitation() {
  return <div className="experience-detail-invitation"><span aria-hidden="true">✳</span><h2>There’s more to the story.</h2><p>Ask about the decisions, challenges, and skills behind this work.</p><Link href="/">Start a conversation <span aria-hidden="true">↗</span></Link></div>;
}

export function JobExperienceDetail({ job, back }: { job: PublicJobDetail; back: string }) {
  return <>
    <Breadcrumbs collection="jobs" title={job.title} back={back} />
    <header className="experience-detail-hero"><span className="experience-monogram" aria-hidden="true">{monogram(job.company || job.title)}</span><div><p className="experience-eyebrow">PROFESSIONAL EXPERIENCE</p><h1>{job.title}</h1><p className="experience-detail-subtitle">{job.company}{job.location && <><span aria-hidden="true"> · </span>{job.location}</>}</p><div className="experience-detail-period"><span>{experiencePeriod(job)}</span>{job.ongoing && <span className="experience-status">Ongoing</span>}</div></div></header>
    <div className="experience-detail-layout"><div className="experience-detail-content">
      <Narrative title="Overview" text={job.summary} />
      <Narrative title="Responsibilities" text={job.responsibilities} />
      <Narrative title="Achievements" text={job.achievements} />
      {job.projects.length > 0 && <section className="experience-related"><div className="experience-results-heading"><h2>Projects from this experience <span>{job.projects.length}</span></h2></div><div className="experience-project-grid">{job.projects.map((project) => <ProjectExperienceCard key={project.id} project={project} related />)}</div></section>}
    </div><aside className="experience-detail-sidebar" aria-label="Experience details"><div className="experience-metadata"><h2>At a glance</h2><dl><MetadataItem label="Company">{job.company}</MetadataItem><MetadataItem label="Location">{job.location}</MetadataItem><MetadataItem label="Period">{experiencePeriod(job)}</MetadataItem>{job.project_count > 0 && <MetadataItem label="Projects">{job.project_count} {job.project_count === 1 ? "project" : "projects"}</MetadataItem>}</dl>{job.skills.length > 0 && <div className="experience-metadata-skills"><h3>Skills & tools</h3><ExperienceSkills skills={job.skills} /></div>}</div><DetailInvitation /></aside></div>
  </>;
}

export function ProjectExperienceDetail({ project, back }: { project: PublicProjectDetail; back: string }) {
  return <>
    <Breadcrumbs collection="projects" title={project.name} back={back} />
    <header className="experience-detail-hero"><span className="experience-monogram" aria-hidden="true">{monogram(project.name)}</span><div><p className="experience-eyebrow">{project.kind === "personal" ? "PERSONAL PROJECT" : "PROFESSIONAL PROJECT"}</p><h1>{project.name}</h1>{(project.role || project.job) && <p className="experience-detail-subtitle">{[project.role, project.job?.company].filter(Boolean).join(" · ")}</p>}<div className="experience-detail-period"><span>{experiencePeriod(project)}</span>{project.ongoing && <span className="experience-status">Ongoing</span>}</div></div></header>
    <div className="experience-detail-layout"><div className="experience-detail-content">
      <Narrative title="Overview" text={project.summary} />
      <Narrative title="About the project" text={project.description} />
      <Narrative title="My contribution" text={project.contribution} />
      <Narrative title="Outcomes" text={project.outcomes} />
    </div><aside className="experience-detail-sidebar" aria-label="Project details"><div className="experience-metadata"><h2>At a glance</h2><dl><MetadataItem label="Type">{project.kind === "personal" ? "Personal project" : "Professional project"}</MetadataItem><MetadataItem label="My role">{project.role}</MetadataItem><MetadataItem label="Period">{experiencePeriod(project)}</MetadataItem>{project.job && <MetadataItem label="Experience"><Link href={`/jobs/${project.job.id}`}>{project.job.title}<span>{project.job.company} <span aria-hidden="true">↗</span></span></Link></MetadataItem>}</dl>{project.skills.length > 0 && <div className="experience-metadata-skills"><h3>Skills & tools</h3><ExperienceSkills skills={project.skills} /></div>}<div className="experience-external-links"><ExternalLink url={project.website_url}>Visit website</ExternalLink><ExternalLink url={project.repository_url}>View repository</ExternalLink></div></div><DetailInvitation /></aside></div>
  </>;
}
