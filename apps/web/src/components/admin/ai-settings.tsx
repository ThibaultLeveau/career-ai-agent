"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminRequest,
  providerNames,
  type Generation,
  type Provider,
  type ProviderStatus,
  type RagSettings,
  type Stage,
} from "@/lib/admin";
import { Notice, useUnsavedChanges } from "./ui";

const providers: Provider[] = ["openai", "anthropic"];

function ModelFields({
  value,
  onChange,
  prefix,
}: {
  value: Generation;
  onChange: (value: Generation) => void;
  prefix: string;
}) {
  return (
    <div className="field-grid">
      <label>
        Provider
        <select
          value={value.provider}
          onChange={(event) =>
            onChange({
              ...value,
              provider: event.target.value as Provider,
              model: "",
            })
          }
        >
          {providers.map((provider) => (
            <option key={provider} value={provider}>
              {providerNames[provider]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Model
        <input
          value={value.model}
          onChange={(event) =>
            onChange({ ...value, model: event.target.value })
          }
          list={`${prefix}-models`}
          placeholder="Select or enter a model ID"
          maxLength={128}
          pattern="[a-zA-Z0-9_.:\-]*"
        />
        <datalist id={`${prefix}-models`}>
          {(value.provider === "openai"
            ? ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"]
            : ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
          ).map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
      </label>
    </div>
  );
}

export function AISettings({
  initial,
  initialProviders,
}: {
  initial: RagSettings;
  initialProviders: ProviderStatus[];
}) {
  const router = useRouter();
  const [settings, setSettings] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [statuses, setStatuses] = useState(initialProviders);
  const [keys, setKeys] = useState<Record<Provider, string>>({
    openai: "",
    anthropic: "",
  });
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState({ message: "", error: false });
  const [tests, setTests] = useState<
    Partial<Record<Stage, { message: string; error: boolean }>>
  >({});
  const dirty = JSON.stringify(settings) !== JSON.stringify(saved);
  const keyDirty = providers.some((provider) => !!keys[provider]);
  useUnsavedChanges(dirty || keyDirty);

  function update<K extends keyof RagSettings>(
    section: K,
    value: RagSettings[K],
  ) {
    setSettings({ ...settings, [section]: value });
    setNotice({ message: "", error: false });
    setTests({});
  }
  async function action(id: string, task: () => Promise<void>) {
    setBusy(id);
    setNotice({ message: "", error: false });
    try {
      await task();
    } catch (error) {
      setNotice({ message: (error as Error).message, error: true });
    } finally {
      setBusy("");
    }
  }
  async function saveKey(provider: Provider, remove = false) {
    if (
      remove &&
      !window.confirm(
        `Remove the ${providerNames[provider]} API key? Stages using it will need a new key.`,
      )
    )
      return;
    await action(provider, async () => {
      await adminRequest(
        `providers/${provider}`,
        remove ? "DELETE" : "PUT",
        remove ? undefined : { key: keys[provider] },
      );
      setStatuses(
        statuses.map((status) =>
          status.provider === provider
            ? { ...status, configured: !remove }
            : status,
        ),
      );
      setKeys({ ...keys, [provider]: "" });
      setTests({});
      setNotice({
        message: `${providerNames[provider]} key ${remove ? "removed" : "saved"}.`,
        error: false,
      });
      router.refresh();
    });
  }
  async function test(stage: Stage) {
    setBusy(`test-${stage}`);
    setTests((current) => ({ ...current, [stage]: undefined }));
    try {
      const result = await adminRequest<{ message: string }>(
        `test/${stage}`,
        "POST",
        { settings, key: keys[settings[stage].provider] || undefined },
      );
      setTests((current) => ({
        ...current,
        [stage]: { message: result.message, error: false },
      }));
    } catch (error) {
      setTests((current) => ({
        ...current,
        [stage]: { message: (error as Error).message, error: true },
      }));
    } finally {
      setBusy("");
    }
  }
  function testControl(stage: Stage) {
    return (
      <div className="test-row">
        <button
          type="button"
          className="button button-small"
          disabled={!!busy || !settings[stage].model}
          onClick={() => test(stage)}
        >
          {busy === `test-${stage}`
            ? "Testing…"
            : `Test ${stage === "embeddings" ? "embeddings" : stage}`}
        </button>
        <Notice error={tests[stage]?.error}>{tests[stage]?.message}</Notice>
      </div>
    );
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    await action("settings", async () => {
      const result = await adminRequest<RagSettings>(
        "settings",
        "PATCH",
        { chat: settings.chat, embeddings: settings.embeddings, reranking: settings.reranking },
      );
      setSaved(result);
      setSettings(result);
      setNotice({ message: "AI settings saved.", error: false });
      router.refresh();
    });
  }

  return (
    <div className="ai-settings">
      <Notice error={notice.error}>{notice.message}</Notice>
      <section className="settings-section">
        <div className="section-intro">
          <h2>Provider connections</h2>
          <p>
            Connect the services behind your AI. Saved keys are encrypted and
            never displayed.
          </p>
        </div>
        <div className="provider-grid">
          {providers.map((provider) => {
            const configured = statuses.some(
              (status) => status.provider === provider && status.configured,
            );
            return (
              <form
                key={provider}
                className="provider-card"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveKey(provider);
                }}
              >
                <fieldset disabled={!!busy}>
                  <div className="provider-heading">
                    <span className={`provider-logo ${provider}`}>
                      {provider === "openai" ? "O" : "A"}
                    </span>
                    <h3>{providerNames[provider]}</h3>
                    <span
                      className={`status ${configured ? "status-ready" : ""}`}
                    >
                      {configured ? "Key saved" : "Not connected"}
                    </span>
                  </div>
                  <p>
                    {provider === "openai"
                      ? "Chat, embeddings, and reranking"
                      : "Chat and reranking"}
                  </p>
                  <label>
                    {provider === "openai" ? "OpenAI" : "Anthropic"} API key
                    <input
                      type="password"
                      value={keys[provider]}
                      placeholder={
                        configured
                          ? "Enter a replacement key"
                          : "Enter your API key"
                      }
                      autoComplete="off"
                      maxLength={4096}
                      required
                      onChange={(event) => {
                        setKeys({ ...keys, [provider]: event.target.value });
                        setTests({});
                      }}
                    />
                  </label>
                  <div className="provider-actions">
                    <button
                      className="button button-small"
                      disabled={!keys[provider] || !!busy}
                    >
                      {busy === provider
                        ? "Updating…"
                        : configured
                          ? "Replace key"
                          : "Save key"}
                    </button>
                    {keys[provider] && (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => setKeys({ ...keys, [provider]: "" })}
                      >
                        Cancel
                      </button>
                    )}
                    {configured && (
                      <button
                        type="button"
                        className="text-button danger-text"
                        onClick={() => saveKey(provider, true)}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </fieldset>
              </form>
            );
          })}
        </div>
      </section>

      <form onSubmit={save} className="settings-form">
        <fieldset disabled={!!busy}>
          <section className="settings-section">
            <div className="section-intro">
              <span className="section-number">01</span>
              <div>
                <h2>Chat model</h2>
                <p>
                  The voice of your portfolio. Choose how answers will be
                  generated.
                </p>
              </div>
            </div>
            <ModelFields
              prefix="chat"
              value={settings.chat}
              onChange={(value) =>
                update("chat", { ...settings.chat, ...value })
              }
            />
            <details className="advanced">
              <summary>Advanced chat settings</summary>
              <div className="advanced-content">
                <label>
                  Maximum output tokens
                  <input
                    type="number"
                    min={128}
                    max={32768}
                    required
                    value={settings.chat.max_output_tokens}
                    onChange={(event) =>
                      update("chat", {
                        ...settings.chat,
                        max_output_tokens: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label>
                  System prompt
                  <textarea
                    rows={4}
                    maxLength={16000}
                    value={settings.chat.system_prompt}
                    onChange={(event) =>
                      update("chat", {
                        ...settings.chat,
                        system_prompt: event.target.value,
                      })
                    }
                  />
                  <small>
                    Instructions for grounded answers about your experience.
                  </small>
                </label>
              </div>
            </details>
            {testControl("chat")}
          </section>

          <section className="settings-section">
            <div className="section-intro">
              <span className="section-number">02</span>
              <div>
                <h2>Embeddings</h2>
                <p>Turn your documents into searchable meaning.</p>
              </div>
              <span className="pill muted-pill">OpenAI</span>
            </div>
            <div className="field-grid">
              <label>
                Embedding model
                <select
                  value={settings.embeddings.model}
                  onChange={(event) => {
                    const model = event.target
                      .value as RagSettings["embeddings"]["model"];
                    update("embeddings", {
                      ...settings.embeddings,
                      model,
                      dimensions:
                        model === "text-embedding-3-small" ? 1536 : 3072,
                    });
                  }}
                >
                  <option value="text-embedding-3-small">
                    text-embedding-3-small
                  </option>
                  <option value="text-embedding-3-large">
                    text-embedding-3-large
                  </option>
                </select>
              </label>
              <label>
                Dimensions
                <input
                  type="number"
                  min={1}
                  max={
                    settings.embeddings.model === "text-embedding-3-small"
                      ? 1536
                      : 3072
                  }
                  required
                  value={settings.embeddings.dimensions}
                  onChange={(event) =>
                    update("embeddings", {
                      ...settings.embeddings,
                      dimensions: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
            <p className="field-hint">
              Embeddings use OpenAI. Anthropic does not provide an embedding
              model.
            </p>
            {testControl("embeddings")}
          </section>

          <section className="settings-section">
            <div className="section-intro">
              <span className="section-number">03</span>
              <div>
                <h2>Reranking</h2>
                <p>Use an LLM to refine the order of retrieved passages.</p>
              </div>
              <label className="switch-label">
                <input
                  className="switch"
                  type="checkbox"
                  role="switch"
                  aria-label="Enable reranking"
                  checked={settings.reranking.enabled}
                  onChange={(event) =>
                    update("reranking", {
                      ...settings.reranking,
                      enabled: event.target.checked,
                    })
                  }
                />
                <span>{settings.reranking.enabled ? "Enabled" : "Off"}</span>
              </label>
            </div>
            {settings.reranking.enabled ? (
              <>
                <ModelFields
                  prefix="reranking"
                  value={settings.reranking}
                  onChange={(value) =>
                    update("reranking", { ...settings.reranking, ...value })
                  }
                />
                <details className="advanced">
                  <summary>Advanced reranking settings</summary>
                  <div className="advanced-content">
                    <label>
                      Reranking output tokens
                      <input
                        type="number"
                        min={128}
                        max={32768}
                        required
                        value={settings.reranking.max_output_tokens}
                        onChange={(event) =>
                          update("reranking", {
                            ...settings.reranking,
                            max_output_tokens: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                  </div>
                </details>
                {testControl("reranking")}
              </>
            ) : (
              <p className="field-hint">
                Optional and off by default. Enabling adds a provider request to
                refine relevance.
              </p>
            )}
          </section>

        </fieldset>
        <p className="field-hint connection-hint">
          Tests use the current form values and make a small, billable provider
          request. They do not save changes.
        </p>
        <div className="save-bar">
          <span>
            {dirty
              ? "You have unsaved AI changes"
              : "AI settings are up to date"}
            {keyDirty && <small>API keys have separate Save buttons.</small>}
          </span>
          <button
            type="button"
            className="button"
            disabled={!dirty || !!busy}
            onClick={() => {
              setSettings(saved);
              setTests({});
              setNotice({ message: "", error: false });
            }}
          >
            Cancel
          </button>
          <button className="button button-primary" disabled={!dirty || !!busy}>
            {busy === "settings" ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
