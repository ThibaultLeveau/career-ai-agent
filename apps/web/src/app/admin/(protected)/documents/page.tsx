import { DocumentsList } from "@/components/admin/content/lists";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";
import type { ResumeDocument } from "@/lib/content";

export default async function Page() {
  const records = await adminData<ResumeDocument[]>("documents");

  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Documents">
        Your resume PDFs, in one place.
      </PageTitle>
      <DocumentsList documents={records} />
    </div>
  );
}
