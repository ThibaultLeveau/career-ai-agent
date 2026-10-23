"use client";

import { useState } from "react";
import { adminRequest, reloadAdmin } from "@/lib/admin";
import { Notice, useUnsavedChanges } from "./ui";

export function CredentialsForm({ username }: { username: string }) {
  const initial = { username, current: "", password: "", confirmation: "" };
  const [values, setValues] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dirty =
    values.username !== username ||
    values.password !== "" ||
    values.confirmation !== "";
  useUnsavedChanges(dirty && !busy);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (values.password !== values.confirmation) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await adminRequest("credentials", "PUT", {
        username: values.username,
        current_password: values.current,
        new_password: values.password || null,
      });
      reloadAdmin("/admin/login");
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  const field = (name: keyof typeof values) => ({
    value: values[name],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setValues({ ...values, [name]: event.target.value }),
  });
  return (
    <form onSubmit={submit} className="settings-form account-form">
      <section className="settings-section">
        <div className="section-intro">
          <h2>Administrator account</h2>
          <p>
            Update your sign-in details. Changes sign you out of all sessions.
          </p>
        </div>
        <fieldset disabled={busy}>
          <label>
            Username
            <input
              {...field("username")}
              autoComplete="username"
              required
              minLength={3}
              maxLength={64}
              pattern="[a-zA-Z0-9_.\-]+"
            />
            <small>
              3–64 characters. Letters, numbers, dots, hyphens, and underscores.
            </small>
          </label>
          <label>
            Current password
            <input
              {...field("current")}
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
            />
            <small>Required to confirm changes to your account.</small>
          </label>
          <div className="form-divider" />
          <label>
            New password <span className="optional">Optional</span>
            <input
              {...field("password")}
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={1024}
            />
            <small>
              At least 12 characters. Leave empty to keep your password.
            </small>
          </label>
          <label>
            Confirm new password
            <input
              {...field("confirmation")}
              type="password"
              autoComplete="new-password"
              required={!!values.password}
              maxLength={1024}
            />
          </label>
        </fieldset>
      </section>
      <Notice error>{error}</Notice>
      <div className="save-bar">
        <span>
          {dirty ? "You have unsaved changes" : "Your account is up to date"}
        </span>
        <button
          type="button"
          className="button"
          disabled={!dirty || busy}
          onClick={() => {
            setValues(initial);
            setError("");
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
