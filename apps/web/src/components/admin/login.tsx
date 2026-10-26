"use client";

import { useState } from "react";
import { adminRequest, reloadAdmin } from "@/lib/admin";
import { Notice } from "./ui";

export function LoginForm() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await adminRequest("login", "POST", {
        username: data.get("username"),
        password: data.get("password"),
      });
      reloadAdmin("/admin");
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="login-form">
      <label>
        Username
        <input
          name="username"
          autoComplete="username"
          required
          maxLength={64}
          autoFocus
        />
      </label>
      <label>
        Password
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          required
          maxLength={1024}
        />
      </label>
      <Notice error>{error}</Notice>
      <button className="button button-primary" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
        <span aria-hidden="true">→</span>
      </button>
    </form>
  );
}
