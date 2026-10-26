import { SkillsList } from "@/components/admin/content/skills-list";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";
import type { Skill } from "@/lib/content";

export default async function Page() {
  const records = await adminData<Skill[]>("skills");

  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Skills">
        Keywords that connect your experience.
      </PageTitle>
      <SkillsList skills={records} />
    </div>
  );
}
