"use client";

import { useState } from "react";
import { adminRequest } from "@/lib/admin";
import type { Skill } from "@/lib/content";
import { Notice } from "../ui";

export function SkillPicker({
  skills: initial,
  selected,
  onChange,
  onBusyChange,
}: {
  skills: Skill[];
  selected: number[];
  onChange: (ids: number[]) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [skills, setSkills] = useState(initial);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const keyword = query.trim();
  const matches = skills.filter((skill) =>
    skill.keyword.toLowerCase().includes(keyword.toLowerCase()),
  );
  async function create() {
    setBusy(true);
    onBusyChange(true);
    setError("");
    try {
      const skill = await adminRequest<Skill>("skills", "POST", { keyword });
      setSkills([...skills, skill]);
      onChange([...selected, skill.id]);
      setQuery("");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  return (
    <div className="skill-picker">
      <label>
        Skills
        <input
          type="search"
          maxLength={100}
          placeholder="Find or create a skill…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div className="skill-options">
        {matches.map((skill) => (
          <label
            className={`skill-option ${selected.includes(skill.id) ? "selected" : ""}`}
            key={skill.id}
          >
            <input
              type="checkbox"
              checked={selected.includes(skill.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...selected, skill.id]
                    : selected.filter((id) => id !== skill.id),
                )
              }
            />
            {skill.keyword}
          </label>
        ))}
        {!skills.length && !keyword && (
          <small>No skills yet. Type a keyword to create one.</small>
        )}
      </div>
      {keyword &&
        !skills.some(
          (skill) => skill.keyword.toLowerCase() === keyword.toLowerCase(),
        ) && (
          <button
            type="button"
            className="button button-small"
            disabled={busy}
            onClick={create}
          >
            {busy ? "Creating…" : `Create “${keyword}”`}
          </button>
        )}
      <Notice error>{error}</Notice>
    </div>
  );
}
