import Link from "next/link";
import { experiencePeriod, monogram, type PublicJob, type PublicProject, type PublicSkill } from "@/lib/public-career";

export function ExperienceSkills({ skills, limit }: { skills: PublicSkill[]; limit?: number }) {
  if (!skills.length) return null;
  const visible = limit ? skills.slice(0, limit) : skills;
  return <ul className="experience-skills" aria-label="Skills">
    {visible.map((skill) => <li key={skill.id}>{skill.keyword}</li>)}
    {limit && skills.length > limit && <li className="experience-skills-more">+{skills.length - limit}</li>}
  </ul>;
}

export function ExperienceArrow() {
  return <svg className="experience-card-arrow" viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function JobExperienceCard({ job, from }: { job: PublicJob; from: string }) {
  return <Link className="experience-card experience-job-card" href={`/jobs/${job.id}?${new URLSearchParams({ from })}`}>
    <div className="experience-card-timeline"><span className="experience-card-date">{experiencePeriod(job)}</span>{job.ongoing && <span className="experience-status">Ongoing</span>}</div>
    <span className="experience-monogram" aria-hidden="true">{monogram(job.company || job.title)}</span>
    <div className="experience-card-body">
      <p className="experience-card-company">{job.company}</p>
      <h2 className="experience-card-title">{job.title}</h2>
      {job.location && <p className="experience-card-meta">{job.location}</p>}
      {job.summary && <p className="experience-card-summary">{job.summary}</p>}
      <ExperienceSkills skills={job.skills} limit={5} />
      {job.project_count > 0 && <span className="experience-card-project-count">{job.project_count} {job.project_count === 1 ? "project" : "projects"}</span>}
    </div>
    <ExperienceArrow />
  </Link>;
}

export function ProjectExperienceCard({ project, from, related = false }: { project: PublicProject; from?: string; related?: boolean }) {
  const Heading = related ? "h3" : "h2";
  const href = `/projects/${project.id}${from ? `?${new URLSearchParams({ from })}` : ""}`;
  return <Link className="experience-card experience-project-card" href={href}>
    <div className="experience-card-topline">
      <span className="experience-monogram" aria-hidden="true">{monogram(project.name)}</span>
      <span className="experience-kind">{project.kind === "personal" ? "Personal" : "Professional"}</span>
      <ExperienceArrow />
    </div>
    <div className="experience-card-body">
      <p className="experience-card-company">{project.job?.company ?? "Independent project"}</p>
      <Heading className="experience-card-title">{project.name}</Heading>
      {project.role && <p className="experience-card-meta">{project.role}</p>}
      {project.summary && <p className="experience-card-summary">{project.summary}</p>}
      <ExperienceSkills skills={project.skills} limit={5} />
    </div>
    <div className="experience-card-footer"><span>{experiencePeriod(project)}</span>{project.ongoing && <span className="experience-status">Ongoing</span>}</div>
  </Link>;
}
