"use client";

import { useState } from "react";
import { adminRequest, type RagSettings } from "@/lib/admin";
import { Notice, useUnsavedChanges } from "./ui";

export function RAGSettings({ initial }: { initial: RagSettings }) {
  const [values, setValues] = useState({
    retrieval: initial.retrieval,
    ingestion: initial.ingestion,
  });
  const [saved, setSaved] = useState(values);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ message: "", error: false });
  const dirty = JSON.stringify(saved) !== JSON.stringify(values);
  useUnsavedChanges(dirty);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice({ message: "", error: false });
    try {
      const result = await adminRequest<RagSettings>(
        "settings",
        "PATCH",
        values,
      );
      const next = { retrieval: result.retrieval, ingestion: result.ingestion };
      setValues(next);
      setSaved(next);
      setNotice({
        message:
          "RAG settings saved. Changed chunking settings require manual re-ingestion of existing content.",
        error: false,
      });
    } catch (error) {
      setNotice({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="settings-form">
      <fieldset disabled={busy}>
        <section className="settings-section">
          <div className="section-intro">
            <div>
              <h2>Retrieval</h2>
              <p>
                Choose how the career assistant finds and expands relevant
                passages. These controls are private to your administration.
              </p>
            </div>
          </div>
          <div className="field-grid">
            <label>
              Search mode
              <select
                aria-label="Search mode"
                value={values.retrieval.mode}
                onChange={(event) =>
                  setValues({
                    ...values,
                    retrieval: {
                      ...values.retrieval,
                      mode: event.target.value as "hybrid" | "semantic",
                    },
                  })
                }
              >
                <option value="hybrid">Hybrid · meaning and keywords</option>
                <option value="semantic">Semantic · meaning</option>
              </select>
              <small>
                Hybrid combines semantic similarity with keyword matches.
              </small>
            </label>
            <label>
              Expansion window
              <input
                aria-label="Expansion window"
                type="number"
                required
                min={0}
                max={5}
                value={values.retrieval.window_size}
                onChange={(event) =>
                  setValues({
                    ...values,
                    retrieval: {
                      ...values.retrieval,
                      window_size: Number(event.target.value),
                    },
                  })
                }
              />
              <small>
                Neighboring chunks to include on each side of a passage. Use 0
                to turn expansion off.
              </small>
            </label>
            {(
              [
                ["candidate_count", "Retrieval candidates", 100],
                [
                  "context_count",
                  "Context passages",
                  values.retrieval.candidate_count,
                ],
              ] as const
            ).map(([key, label, max]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  required
                  min={1}
                  max={max}
                  value={values.retrieval[key]}
                  onChange={(e) =>
                    setValues({
                      ...values,
                      retrieval: {
                        ...values.retrieval,
                        [key]: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            ))}
          </div>
        </section>
        <section className="settings-section">
          <div className="section-intro">
            <div>
              <h2>Ingestion</h2>
              <p>
                New and edited content is ingested automatically. Re-ingest
                existing content after changing chunking or embedding settings.
              </p>
            </div>
          </div>
          <div className="field-grid">
            {(
              [
                ["chunk_size", "Chunk size (tokens)", 100, 8000],
                [
                  "chunk_overlap",
                  "Chunk overlap (tokens)",
                  0,
                  values.ingestion.chunk_size - 1,
                ],
                ["max_retries", "Retries per ingestion job", 0, 10],
              ] as const
            ).map(([key, label, min, max]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  required
                  min={min}
                  max={max}
                  value={values.ingestion[key]}
                  onChange={(e) =>
                    setValues({
                      ...values,
                      ingestion: {
                        ...values.ingestion,
                        [key]: Number(e.target.value),
                      },
                    })
                  }
                />
                {key === "max_retries" && (
                  <small>
                    Additional attempts after a transient failure. Permanent
                    errors fail immediately.
                  </small>
                )}
              </label>
            ))}
          </div>
        </section>
      </fieldset>
      <Notice error={notice.error}>{notice.message}</Notice>
      <div className="save-bar">
        <span>
          {dirty
            ? "You have unsaved RAG changes"
            : "RAG settings are up to date"}
        </span>
        <button
          type="button"
          className="button"
          disabled={!dirty || busy}
          onClick={() => {
            setValues(saved);
            setNotice({ message: "", error: false });
          }}
        >
          Cancel
        </button>
        <button className="button button-primary" disabled={!dirty || busy}>
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
