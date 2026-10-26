"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { adminRequest } from "@/lib/admin";
import {
  activeStatus,
  type HistorySourceType,
  type IngestionSummary,
} from "@/lib/ingestion";
import { ActionMenu, type MenuAction } from "../action-menu";
import { StatusTooltip, useIngestion } from "../ingestion-status";
import { Notice } from "../ui";

export function RecordRow({
  collection,
  recordId,
  label,
  initial,
  children,
  onEdit,
  editing,
  deleteMessage,
}: {
  collection: HistorySourceType;
  recordId: number;
  label: string;
  initial?: IngestionSummary;
  children: React.ReactNode;
  onEdit?: () => void;
  editing?: boolean;
  deleteMessage?: string;
}) {
  const row = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const { value, status, busy, error, statusError, reingest } = useIngestion({
    sourceType: collection === "skills" ? undefined : collection,
    recordId,
    initial,
  });
  async function remove() {
    if (
      !window.confirm(
        deleteMessage ?? `Delete ${label}? This cannot be undone.`,
      )
    )
      return;
    setDeleting(true);
    setDeleteError("");
    try {
      await adminRequest(`${collection}/${recordId}`, "DELETE");
      router.refresh();
    } catch (error) {
      setDeleteError((error as Error).message);
    } finally {
      setDeleting(false);
    }
  }
  const actions: MenuAction[] = [
    onEdit
      ? { label: "Edit", onSelect: onEdit }
      : { label: "Edit", href: `/admin/${collection}/${recordId}` },
  ];
  if (collection !== "skills")
    actions.push({
      label: "Re-ingest",
      onSelect: reingest,
      disabled: busy || activeStatus(status),
    });
  if (collection === "documents")
    actions.push({
      label: "Download",
      href: `/api/admin/documents/${recordId}/file`,
      download: true,
    });
  actions.push({
    label: deleting ? "Deleting…" : "Delete",
    onSelect: remove,
    disabled: deleting,
    danger: true,
  });
  return (
    <div className="record-row-group">
      <div className="content-row" ref={row}>
        {children}
        {!editing && (
          <div className="record-actions">
            {collection !== "skills" && (
              <StatusTooltip
                status={status}
                error={value?.error || statusError}
                href={
                  value?.job_id
                    ? `/admin/ingestion?job=${value.job_id}`
                    : "/admin/ingestion"
                }
              />
            )}
            <ActionMenu label={label} actions={actions} target={row} />
          </div>
        )}
      </div>
      <Notice error>{deleteError || error}</Notice>
    </div>
  );
}
