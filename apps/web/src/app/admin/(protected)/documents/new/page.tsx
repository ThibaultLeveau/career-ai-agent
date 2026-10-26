import { DocumentForm } from "@/components/admin/content/document-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";

export default async function Page() {
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/documents">
        ← Documents
      </Link>
      <PageTitle eyebrow="DOCUMENTS" title="New document">
        Add your document details.
      </PageTitle>
      <DocumentForm />
    </div>
  );
}
