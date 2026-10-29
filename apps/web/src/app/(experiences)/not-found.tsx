import Link from "next/link";

export default function ExperienceNotFound() {
  return <div className="experience-state"><span className="experience-eyebrow">404 / EXPERIENCE NOT FOUND</span><h1>This part of the story isn’t here.</h1><p>The experience may have been removed, or the link may be incorrect.</p><div><Link href="/jobs">Explore jobs</Link><Link href="/projects">Explore projects</Link></div></div>;
}
