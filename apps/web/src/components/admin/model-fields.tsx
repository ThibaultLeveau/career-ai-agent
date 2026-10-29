"use client";

import { providerNames, type Generation, type Provider } from "@/lib/admin";

const providers: Provider[] = ["openai", "anthropic"];

export function ModelFields({
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
