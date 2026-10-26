"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { adminRequest } from "@/lib/admin";
import { fileSize, type ResumeDocument } from "@/lib/content";
import { Notice, useUnsavedChanges } from "../ui";
import { DeleteButton, Field, SaveBar } from "./shared";

export function DocumentForm({ document }: { document?: ResumeDocument }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(document?.title ?? "");
  const [savedTitle, setSavedTitle] = useState(title);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty = title !== savedTitle || file !== null;
  useUnsavedChanges(dirty);
  function reset() {
    setTitle(savedTitle);
    setFile(null);
    setError("");
    setMessage("");
    if (input.current) input.current.value = "";
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (
      file &&
      (file.size > 10 * 1024 * 1024 ||
        !file.name.toLowerCase().endsWith(".pdf") ||
        file.type !== "application/pdf")
    ) {
      setError("Choose a PDF file of 10 MiB or smaller.");
      return;
    }
    setBusy(true);
    try {
      const body = new FormData();
      body.set("title", title);
      if (file) body.set("file", file);
      const result = await adminRequest<ResumeDocument>(
        document ? `documents/${document.id}` : "documents",
        document ? "PUT" : "POST",
        body,
      );
      setSavedTitle(title);
      setFile(null);
      setMessage("Document saved.");
      if (input.current) input.current.value = "";
      if (!document) router.replace(`/admin/documents/${result.id}`);
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="settings-section content-form">
          <Field
            label="Title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          {document && (
            <div className="document-current">
              <strong>{document.filename}</strong>
              <small>
                {fileSize(document.size)} · Uploaded{" "}
                {document.created_at.slice(0, 10)}
              </small>
              <a
                className="button button-small"
                href={`/api/admin/documents/${document.id}/file`}
                download
              >
                Download PDF
              </a>
            </div>
          )}
          <label>
            {document ? "Replace PDF" : "Resume PDF"}
            <input
              ref={input}
              type="file"
              accept="application/pdf,.pdf"
              required={!document}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <small>
              PDF only, up to 10 MiB.
              {document && " Leave empty to keep the current file."}
            </small>
          </label>
        </fieldset>
        <Notice error>{error}</Notice>
        <Notice>{message}</Notice>
        <SaveBar busy={busy} dirty={dirty} isNew={!document} reset={reset} />
      </form>
      {document && (
        <div className="record-footer">
          <DeleteButton
            path={`documents/${document.id}`}
            label={document.title}
            returnTo="/admin/documents"
          />
        </div>
      )}
    </>
  );
}
