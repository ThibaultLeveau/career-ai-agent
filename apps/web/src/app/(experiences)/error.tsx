"use client";

import Link from "next/link";

export default function ExperienceError({ retry }: { retry: () => void }) {
  return <div className="experience-state" role="alert"><span className="experience-state-mark" aria-hidden="true">✳</span><h1>These experiences couldn’t be loaded.</h1><p>Please try again in a moment.</p><div><button type="button" onClick={retry}>Try again</button><Link href="/">Back to the conversation</Link></div></div>;
}
