"use client";

import { useState } from "react";
import { adminRequest, providerNames, type AgentRole, type AgentSettings, type AgentsSettings, type RagSettings } from "@/lib/admin";
import { ModelFields } from "./model-fields";
import { Notice, useUnsavedChanges } from "./ui";

const roles: { id: AgentRole; name: string; description: string }[] = [
  { id: "query_analyzer", name: "Query Analyzer", description: "Chooses searches, combines filters, and checks whether there is enough evidence to answer." },
  { id: "database", name: "Database", description: "Finds and counts matching career records using structured filters." },
  { id: "rag", name: "RAG", description: "Finds relevant passages, including within records selected by the Database agent." },
  { id: "representative", name: "Thibault Representative", description: "Turns the gathered evidence into a clear answer in the visitor’s language." },
];

export function AgentsSettingsForm({ initial, defaults }: { initial: RagSettings; defaults: AgentsSettings }) {
  const [values, setValues] = useState(initial.agents);
  const [saved, setSaved] = useState(initial.agents);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState({ message: "", error: false });
  const [tests, setTests] = useState<Partial<Record<AgentRole, { message: string; error: boolean }>>>({});
  const dirty = JSON.stringify(saved) !== JSON.stringify(values);
  useUnsavedChanges(dirty);

  function update(role: AgentRole, value: AgentSettings) {
    setValues((current) => ({ ...current, [role]: value }));
    setNotice({ message: "", error: false });
    setTests((current) => ({ ...current, [role]: undefined }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy("save");
    setNotice({ message: "", error: false });
    try {
      const result = await adminRequest<RagSettings>("settings", "PATCH", { agents: values });
      setValues(result.agents);
      setSaved(result.agents);
      setNotice({ message: "Agent settings saved. Changes apply to the next question.", error: false });
    } catch (error) {
      setNotice({ message: (error as Error).message, error: true });
    } finally {
      setBusy("");
    }
  }

  async function test(role: AgentRole) {
    setBusy(role);
    setTests((current) => ({ ...current, [role]: undefined }));
    try {
      const result = await adminRequest<{ message: string }>(`test/${role}`, "POST", {
        settings: { ...initial, agents: values },
      });
      setTests((current) => ({ ...current, [role]: { message: result.message, error: false } }));
    } catch (error) {
      setTests((current) => ({ ...current, [role]: { message: (error as Error).message, error: true } }));
    } finally {
      setBusy("");
    }
  }

  return (
    <form className="settings-form" onSubmit={save}>
      <fieldset disabled={!!busy}>
        <section className="settings-section">
          <div className="section-intro">
            <div>
              <h2>Agentic mode</h2>
              <p>Combine exact database searches with semantic retrieval before writing an answer. When disabled, the existing RAG chat answers directly.</p>
            </div>
            <label className="switch-label">
              <input className="switch" type="checkbox" role="switch" aria-label="Enable agentic mode" checked={values.enabled} onChange={(event) => {
                setValues({ ...values, enabled: event.target.checked });
                setNotice({ message: "", error: false });
              }} />
              <span>{values.enabled ? "Enabled" : "Disabled"}</span>
            </label>
          </div>
          <p className="field-hint">Agents use the chat model from AI Provider unless you choose an override below. Agentic mode can use more model requests per question.</p>
        </section>
        {roles.map(({ id, name, description }) => {
          const value = values[id];
          const generation = value.generation ?? initial.chat;
          return (
            <section className="settings-section agent-settings" key={id} aria-label={name}>
              <div className="section-intro"><div><h2>{name}</h2><p>{description}</p></div></div>
              <label htmlFor={`agent-${id}-prompt`}>{name} prompt</label>
              <textarea id={`agent-${id}-prompt`} rows={8} maxLength={16000} value={value.prompt} onChange={(event) => update(id, { ...value, prompt: event.target.value })} />
              <div className="agent-prompt-actions">
                <small>Customize this agent’s instructions. Tool access and evidence requirements remain enforced by the application.</small>
                <button className="text-button" type="button" disabled={value.prompt === defaults[id].prompt} onClick={() => update(id, { ...value, prompt: defaults[id].prompt })}>Reset {name} prompt</button>
              </div>
              <label className="agent-model-toggle">
                <input type="checkbox" checked={value.generation !== null} onChange={(event) => update(id, {
                  ...value,
                  generation: event.target.checked ? {
                    provider: initial.chat.provider,
                    model: initial.chat.model,
                    max_output_tokens: initial.chat.max_output_tokens,
                  } : null,
                })} />
                Use a different model for {name}
              </label>
              {value.generation ? (
                <div className="agent-generation">
                  <ModelFields prefix={`agent-${id}`} value={value.generation} onChange={(next) => update(id, { ...value, generation: next })} />
                  <label>
                    Maximum output tokens
                    <input type="number" min={128} max={32768} required value={value.generation.max_output_tokens} onChange={(event) => update(id, { ...value, generation: { ...generation, max_output_tokens: Number(event.target.value) } })} />
                  </label>
                </div>
              ) : <p className="field-hint">Uses {providerNames[initial.chat.provider]} · {initial.chat.model || "No chat model selected"} · {initial.chat.max_output_tokens.toLocaleString()} maximum output tokens.</p>}
              <div className="test-row">
                <button className="button button-small" type="button" disabled={!!busy || !generation.model} onClick={() => void test(id)}>{busy === id ? "Testing…" : `Test ${name}`}</button>
                <Notice error={tests[id]?.error}>{tests[id]?.message}</Notice>
              </div>
              <p className="field-hint">Test uses these draft settings and your saved provider key. It makes a small billable request and does not save changes.</p>
            </section>
          );
        })}
      </fieldset>
      <Notice error={notice.error}>{notice.message}</Notice>
      <div className="save-bar">
        <span>{dirty ? "You have unsaved agent changes" : "Agent settings are up to date"}</span>
        <button type="button" className="button" disabled={!dirty || !!busy} onClick={() => {
          setValues(saved);
          setNotice({ message: "", error: false });
          setTests({});
        }}>Cancel</button>
        <button className="button button-primary" disabled={!dirty || !!busy}>{busy === "save" ? "Saving…" : "Save changes"}</button>
      </div>
    </form>
  );
}
