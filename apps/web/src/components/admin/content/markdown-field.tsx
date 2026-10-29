"use client";

import dynamic from "next/dynamic";
import { useId, useState } from "react";

const VisualEditor = dynamic(() => import("./markdown-visual-editor"), {
  ssr: false,
  loading: () => <p className="markdown-loading">Loading editor…</p>,
});

export const MARKDOWN_LIMIT = 8000;
export const SMALL_SUMMARY_LIMIT = 280;
export const characterCount = (value: string) => Array.from(value).length;

export function MarkdownField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const id = useId();
  const [mode, setMode] = useState<"visual" | "markdown">("visual");
  const [parseError, setParseError] = useState(false);
  const count = characterCount(value);
  const invalid = count > MARKDOWN_LIMIT;
  const changeMode = (next: "visual" | "markdown") => {
    setParseError(false);
    setMode(next);
  };

  return (
    <div className="markdown-field" role="group" aria-labelledby={`${id}-label`}>
      <div className="markdown-field-heading">
        <span id={`${id}-label`} className="content-field-label">{label}</span>
        <div className="markdown-modes" aria-label={`${label} editor mode`}>
          <button type="button" aria-pressed={mode === "visual"} disabled={disabled} onClick={() => changeMode("visual")}>Visual</button>
          <button type="button" aria-pressed={mode === "markdown"} disabled={disabled} onClick={() => changeMode("markdown")}>Markdown</button>
        </div>
      </div>
      <div className={`markdown-editor-frame${invalid ? " field-invalid" : ""}`}>
        {mode === "visual" ? (
          <VisualEditor
            value={value}
            label={label}
            onChange={onChange}
            disabled={disabled || parseError}
            onError={() => setParseError(true)}
          />
        ) : (
          <textarea
            className="markdown-source"
            aria-label={`${label} Markdown`}
            aria-describedby={`${id}-count`}
            aria-invalid={invalid}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
            rows={7}
            spellCheck={false}
          />
        )}
      </div>
      {parseError && (
        <p className="markdown-error" role="alert">
          This content cannot be displayed in Visual mode. Your Markdown is preserved. <button type="button" className="text-button" disabled={disabled} onClick={() => changeMode("markdown")}>Edit Markdown</button>
        </p>
      )}
      <small id={`${id}-count`} className={invalid ? "markdown-error" : "field-counter"} role={invalid ? "alert" : undefined}>
        {count.toLocaleString()} / {MARKDOWN_LIMIT.toLocaleString()} characters{invalid ? " — shorten this field before saving." : " · Saved as Markdown"}
      </small>
    </div>
  );
}
