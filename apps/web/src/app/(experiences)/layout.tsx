import { PublicHeader } from "@/components/public-header";
import "../portfolio.css";
import "../experiences.css";

export default function ExperiencesLayout({ children }: { children: React.ReactNode }) {
  return <div className="portfolio experiences"><a href="#main-content" className="portfolio-skip">Skip to content</a><PublicHeader /><main id="main-content" className="experience-main">{children}</main></div>;
}
