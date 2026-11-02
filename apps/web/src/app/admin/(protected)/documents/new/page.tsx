import { DocumentForm } from "@/components/admin/content/document-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";
import { adminData } from "@/lib/admin-server";
import type { DocumentType } from "@/lib/content";

export default async function Page() {
  const documentTypes = await adminData<DocumentType[]>("document-types");
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/documents">
        ← Documents
      </Link>
      <PageTitle eyebrow="DOCUMENTS" title="New document">
        Add your document details.
      </PageTitle>
      <DocumentForm documentTypes={documentTypes} />
    </div>
  );
}
