"use client";

import { useId, useRef, useState } from "react";
import { adminRequest } from "@/lib/admin";
import { MARKDOWN_LIMIT, SMALL_SUMMARY_LIMIT, characterCount } from "./markdown-field";

export function SmallSummaryField({
  value,
  overview,
  onChange,
  disabled,
  onBusyChange,
}: {
  value: string;
  overview: string;
  onChange: (value: string) => void;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
}) {
  const id = useId();
  const pending = useRef(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const count = characterCount(value);
  const invalid = count > SMALL_SUMMARY_LIMIT;
  const overviewReady = Boolean(overview.trim()) && characterCount(overview) <= MARKDOWN_LIMIT;

  async function generate() {
    if (pending.current || disabled || !overviewReady) return;
    pending.current = true;
    setGenerating(true);
    setError("");
    onBusyChange(true);
    try {
      const result = await adminRequest<{ small_summary: string }>("content/small-summary", "POST", { overview });
      if (typeof result.small_summary !== "string" || !result.small_summary.trim() || characterCount(result.small_summary) > SMALL_SUMMARY_LIMIT) {
        throw new Error("The generated summary was not valid. Please try again.");
      }
      onChange(result.small_summary);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      pending.current = false;
      setGenerating(false);
      onBusyChange(false);
    }
  }

  return (
    <div className="small-summary-field">
      <div className="markdown-field-heading">
        <label htmlFor={id}>Small Summary</label>
        <button type="button" className="button button-small" disabled={disabled || generating || !overviewReady} onClick={generate}>
          {generating ? "Generating…" : "AI Generation"}
        </button>
      </div>
      <textarea
        id={id}
        rows={3}
        value={value}
        aria-describedby={`${id}-help`}
        aria-invalid={invalid}
        disabled={disabled || generating}
        onChange={(event) => onChange(Array.from(event.target.value).slice(0, SMALL_SUMMARY_LIMIT).join(""))}
      />
      <small id={`${id}-help`} className={invalid ? "markdown-error" : "field-counter"}>
        {count} / {SMALL_SUMMARY_LIMIT} characters · Shown only in lists. {overviewReady ? "Generate from your current Overview, then review and save." : "Fill in Overview to enable AI Generation."}
      </small>
      {error && <p className="markdown-error" role="alert">{error}</p>}
    </div>
  );
}
