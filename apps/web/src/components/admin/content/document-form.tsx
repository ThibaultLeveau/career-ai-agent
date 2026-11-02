"use client";

import { IngestionStatus } from "../ingestion-status";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { adminRequest } from "@/lib/admin";
import { fileSize, type DocumentType, type ResumeDocument } from "@/lib/content";
import { Notice, useUnsavedChanges } from "../ui";
import { DeleteButton, Field, SaveBar } from "./shared";

function fields(document?: ResumeDocument) {
  return {
    title: document?.title ?? "",
    document_type_key: document?.document_type_key ?? "other",
    available_in_chat: document?.available_in_chat ?? false,
    matching_notes: document?.matching_notes ?? "",
  };
}

export function DocumentForm({
  document,
  documentTypes,
}: {
  document?: ResumeDocument;
  documentTypes: DocumentType[];
}) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [values, setValues] = useState(fields(document));
  const [saved, setSaved] = useState(values);
  const [types, setTypes] = useState(documentTypes);
  const [typeName, setTypeName] = useState("");
  const [creatingType, setCreatingType] = useState(false);
  const [typeError, setTypeError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty = JSON.stringify(values) !== JSON.stringify(saved) || file !== null;
  useUnsavedChanges(dirty);
  function reset() {
    setValues(saved);
    setFile(null);
    setTypeName("");
    setTypeError("");
    setError("");
    setMessage("");
    if (input.current) input.current.value = "";
  }
  function selectType(key: string) {
    setValues((current) => ({
      ...current,
      document_type_key: key,
      available_in_chat: key === current.document_type_key && current.available_in_chat,
    }));
  }
  async function createType() {
    if (!typeName.trim() || creatingType) return;
    setCreatingType(true);
    setTypeError("");
    try {
      const result = await adminRequest<DocumentType>("document-types", "POST", {
        name: typeName.trim(),
      });
      setTypes((current) => [...current, result]);
      selectType(result.key);
      setTypeName("");
    } catch (error) {
      setTypeError((error as Error).message);
    } finally {
      setCreatingType(false);
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || creatingType) return;
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
      body.set("title", values.title);
      body.set("document_type_key", values.document_type_key);
      body.set("available_in_chat", String(values.available_in_chat));
      body.set("matching_notes", values.matching_notes);
      if (file) body.set("file", file);
      const result = await adminRequest<ResumeDocument>(
        document ? `documents/${document.id}` : "documents",
        document ? "PUT" : "POST",
        body,
      );
      setValues(fields(result));
      setSaved(fields(result));
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
      {document && (
        <IngestionStatus
          sourceType="documents"
          recordId={document.id}
          initial={document.ingestion}
        />
      )}
      <form onSubmit={submit}>
        <fieldset disabled={busy || creatingType} className="settings-section content-form">
          <Field
            label="Title"
            required
            value={values.title}
            onChange={(e) => setValues({ ...values, title: e.target.value })}
          />
          <div className="document-type-field">
            <label>
              Document type
              <select value={values.document_type_key} onChange={(e) => selectType(e.target.value)}>
                {types.map((type) => <option key={type.key} value={type.key}>{type.name}</option>)}
              </select>
            </label>
            <details className="document-type-create">
              <summary>Add a document type</summary>
              <div className="document-type-create-fields">
                <label>
                  New document type
                  <input
                    value={typeName}
                    maxLength={100}
                    placeholder="For example, Certificate"
                    onChange={(e) => setTypeName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void createType();
                      }
                    }}
                  />
                </label>
                <button className="button button-small" type="button" disabled={!typeName.trim()} onClick={createType}>
                  {creatingType ? "Adding…" : "Add type"}
                </button>
              </div>
              <Notice error>{typeError}</Notice>
            </details>
          </div>
          {values.document_type_key === "resume" && (
            <section className="document-sharing" aria-label="Resume sharing">
              <label className="switch-label">
                <input
                  className="switch"
                  type="checkbox"
                  role="switch"
                  checked={values.available_in_chat}
                  onChange={(e) => setValues({ ...values, available_in_chat: e.target.checked })}
                  aria-describedby="resume-sharing-help"
                />
                Available in chat
              </label>
              <p id="resume-sharing-help">Allow visitors to download this resume when it fits their job opportunity. Turning this off also disables existing download links.</p>
              <label>
                Matching notes
                <textarea
                  rows={3}
                  maxLength={2000}
                  value={values.matching_notes}
                  placeholder="For example, English resume for senior backend or Python engineering roles."
                  onChange={(e) => setValues({ ...values, matching_notes: e.target.value })}
                />
                <small>Help the assistant choose this resume: roles, seniority, language or location. These notes are not shown to visitors.</small>
              </label>
            </section>
          )}
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
            {document ? "Replace PDF" : "Document PDF"}
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
        <SaveBar busy={busy || creatingType} dirty={dirty} isNew={!document} reset={reset} />
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
