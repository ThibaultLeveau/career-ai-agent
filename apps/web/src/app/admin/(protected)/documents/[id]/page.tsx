import { DocumentForm } from "@/components/admin/content/document-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";
import { adminData } from "@/lib/admin-server";
import type { ResumeDocument } from "@/lib/content";
import { notFound } from "next/navigation";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[1-9]\d*$/.test(id)) notFound();
  const record = await adminData<ResumeDocument>(`documents/${id}`);
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/documents">
        ← Documents
      </Link>
      <PageTitle eyebrow="DOCUMENTS" title="Edit document">
        Update your document details.
      </PageTitle>
      <DocumentForm document={record} />
    </div>
  );
}
