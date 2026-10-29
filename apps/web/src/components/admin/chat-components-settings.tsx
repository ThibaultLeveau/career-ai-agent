"use client";

import { useState } from "react";
import { adminRequest, type RagSettings } from "@/lib/admin";
import { Notice, useUnsavedChanges } from "./ui";

export function ChatComponentsSettings({ initial }: { initial: RagSettings["chat_components"] }) {
  const [values, setValues] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState({ message: "", error: false });
  const dirty = JSON.stringify(saved) !== JSON.stringify(values);
  useUnsavedChanges(dirty);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice({ message: "", error: false });
    try {
      const result = await adminRequest<RagSettings>("settings", "PATCH", { chat_components: values });
      setValues(result.chat_components);
      setSaved(result.chat_components);
      setNotice({ message: "Chat component settings saved. New lists will use these page sizes.", error: false });
    } catch (error) {
      setNotice({ message: (error as Error).message, error: true });
    } finally { setBusy(false); }
  }
  return <form className="settings-form" onSubmit={submit}>
    <fieldset disabled={busy}>
      <section className="settings-section">
        <div className="section-intro"><div><h2>Lists in chat</h2><p>Keep results easy to explore. Each list includes a text filter and pagination.</p></div></div>
        <div className="field-grid">{([
          ["project_list_page_size", "Projects per page"],
          ["job_list_page_size", "Jobs per page"],
        ] as const).map(([key, label]) => <label key={key}>{label}
          <input type="number" min={1} max={20} step={1} required value={values[key]}
            onChange={(event) => setValues({ ...values, [key]: Number(event.target.value) })} />
          <small>Default: 5. Choose between 1 and 20.</small>
        </label>)}</div>
        <p className="field-help">Project page size also applies to projects shown beneath a job card. Existing lists retain their page sizes.</p>
      </section>
    </fieldset>
    <Notice error={notice.error}>{notice.message}</Notice>
    <div className="save-bar"><span>{dirty ? "You have unsaved changes" : "Chat component settings are up to date"}</span>
      <button className="button" type="button" disabled={!dirty || busy} onClick={() => { setValues(saved); setNotice({ message: "", error: false }); }}>Cancel</button>
      <button className="button button-primary" type="submit" disabled={!dirty || busy}>{busy ? "Saving…" : "Save changes"}</button>
    </div>
  </form>;
}
