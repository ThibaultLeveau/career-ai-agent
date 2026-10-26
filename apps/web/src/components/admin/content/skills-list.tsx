"use client";

import { IngestionStatus } from "../ingestion-status";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminRequest } from "@/lib/admin";
import type { Skill } from "@/lib/content";
import { Notice, useUnsavedChanges } from "../ui";
import { DeleteButton, Empty, ListToolbar } from "./shared";

function SkillRow({ skill }: { skill: Skill }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [keyword, setKeyword] = useState(skill.keyword);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useUnsavedChanges(editing && keyword !== skill.keyword);
  async function rename(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await adminRequest(`skills/${skill.id}`, "PUT", { keyword });
      setEditing(false);
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="skill-row">
      <div className="content-row">
        {editing ? (
          <form onSubmit={rename} className="inline-form">
            <input
              aria-label="Skill keyword"
              maxLength={100}
              required
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              autoFocus
              disabled={busy}
            />
            <button
              className="button button-small"
              disabled={busy || !keyword.trim()}
            >
              {busy ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              className="text-button"
              disabled={busy}
              onClick={() => {
                setKeyword(skill.keyword);
                setEditing(false);
                setError("");
              }}
            >
              Cancel
            </button>
          </form>
        ) : (
          <>
            <strong className="record-link">{skill.keyword}</strong>
            <button
              className="text-button"
              onClick={() => {
                setKeyword(skill.keyword);
                setEditing(true);
              }}
            >
              Rename
            </button>
          </>
        )}
        <IngestionStatus
          sourceType="skills"
          recordId={skill.id}
          initial={skill.ingestion}
        />
        {!editing && (
          <DeleteButton
            path={`skills/${skill.id}`}
            label={skill.keyword}
            message={`Delete “${skill.keyword}”? It will be removed from all projects. Projects will be kept.`}
          />
        )}
      </div>
      <Notice error>{error}</Notice>
    </div>
  );
}

export function SkillsList({ skills }: { skills: Skill[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [keyword, setKeyword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useUnsavedChanges(!!keyword);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await adminRequest("skills", "POST", { keyword });
      setKeyword("");
      setQuery("");
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const filtered = skills.filter((skill) =>
    skill.keyword.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <form onSubmit={create} className="inline-form skill-create">
        <input
          aria-label="New skill keyword"
          placeholder="New keyword…"
          required
          maxLength={100}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          disabled={busy}
        />
        <button
          className="button button-primary"
          disabled={busy || !keyword.trim()}
        >
          {busy ? "Adding…" : "Add skill"}
        </button>
      </form>
      <Notice error>{error}</Notice>
      <ListToolbar query={query} setQuery={setQuery} label="Skills" />
      <div className="content-list">
        {filtered.map((skill) => (
          <SkillRow key={skill.id} skill={skill} />
        ))}
        {!filtered.length && (
          <Empty>
            {skills.length
              ? "No matching skills."
              : "No skills yet. Add a keyword to get started."}
          </Empty>
        )}
      </div>
    </>
  );
}
