"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  completedHistory,
  readChatStream,
  type ChatSource,
  type ChatTurn,
} from "@/lib/chat";

const prompts = [
  { title: "The career overview", question: "Give me an overview of your career." },
  { title: "Projects & impact", question: "Which projects best show the impact of your work?" },
  { title: "A fit for my team?", question: "How can I tell whether your experience fits the role I’m hiring for?" },
];

function Arrow({ diagonal = false }: { diagonal?: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d={diagonal ? "M6 18 18 6M6 6h12v12" : "M12 19V5m-6 6 6-6 6 6"}
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function InlineText({ text }: { text: string }) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function Answer({ text }: { text: string }) {
  return text.split(/\n\s*\n/).map((paragraph, index) => {
    const lines = paragraph.split("\n");
    if (lines.every((line) => /^\s*[-*] /.test(line))) {
      return (
        <ul key={index}>
          {lines.map((line, item) => (
            <li key={item}><InlineText text={line.replace(/^\s*[-*] /, "")} /></li>
          ))}
        </ul>
      );
    }
    return <p key={index}><InlineText text={paragraph.replace(/^#{1,6}\s+/gm, "")} /></p>;
  });
}

function SourceList({ sources }: { sources: ChatSource[] }) {
  if (!sources.length) return null;
  return (
    <details className="chat-sources">
      <summary>Sources <span>{sources.length}</span></summary>
      <ul>
        {sources.map((source) => (
          <li key={source.id}>
            <span className="source-kind">
              {source.source_type === "document" ? "Document" : source.source_type === "job" ? "Experience" : "Project"}
            </span>
            <span>{source.label}</span>
            {source.page_start !== null && (
              <small>
                {source.page_end !== null && source.page_end !== source.page_start
                  ? `Pages ${source.page_start}–${source.page_end}`
                  : `Page ${source.page_start}`}
              </small>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function CareerChat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  const active = useRef<{ id: number; controller: AbortController } | null>(null);
  const follow = useRef(true);

  useEffect(() => {
    function onScroll() {
      follow.current = document.documentElement.scrollHeight - window.innerHeight - window.scrollY < 180;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      active.current?.controller.abort();
    };
  }, []);

  useEffect(() => {
    if (turns.length && follow.current) bottom.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  useEffect(() => {
    if (!input.current) return;
    input.current.style.height = "auto";
    input.current.style.height = `${Math.min(input.current.scrollHeight, 160)}px`;
  }, [draft]);

  function updateTurn(id: number, update: Partial<ChatTurn> | ((turn: ChatTurn) => Partial<ChatTurn>)) {
    setTurns((current) => current.map((turn) => turn.id === id
      ? { ...turn, ...(typeof update === "function" ? update(turn) : update) }
      : turn));
  }

  async function send(question: string, retryId?: number) {
    const message = question.trim();
    if (!message || active.current) return;
    const id = retryId ?? ++nextId.current;
    const previous = retryId === undefined ? turns : turns.filter((turn) => turn.id !== retryId);
    const history = completedHistory(previous);
    while (new TextEncoder().encode(JSON.stringify({ message, history })).byteLength > 65536)
      history.splice(0, 2);
    const request = { id, controller: new AbortController() };
    active.current = request;
    follow.current = true;
    const turn: ChatTurn = { id, question: message, answer: "", status: "pending", sources: [] };
    setTurns([...previous, turn]);
    setDraft("");
    setBusy(true);
    setAnnouncement("Thinking about your question.");
    input.current?.focus();
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history }),
        signal: request.controller.signal,
        cache: "no-store",
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(typeof error?.detail === "string"
          ? error.detail
          : "My career assistant is temporarily unavailable. Please try again shortly.");
      }
      const sources = await readChatStream(response, (text) => {
        if (active.current === request)
          updateTurn(id, (current) => ({ answer: current.answer + text }));
      });
      if (active.current !== request) return;
      updateTurn(id, { status: "complete", sources });
      setAnnouncement("Response ready. You can read it in the conversation.");
    } catch (error) {
      if (active.current !== request) return;
      const message = error instanceof Error && error.name !== "TypeError" && error.name !== "SyntaxError"
        ? error.message
        : "The connection was interrupted. Please try again.";
      updateTurn(id, { status: "error", error: message });
      setAnnouncement("The response could not be completed. You can try again.");
    } finally {
      if (active.current === request) {
        active.current = null;
        setBusy(false);
      }
    }
  }

  function stop() {
    const request = active.current;
    if (!request) return;
    active.current = null;
    request.controller.abort();
    updateTurn(request.id, { status: "stopped" });
    setBusy(false);
    setAnnouncement("Response stopped.");
    input.current?.focus();
  }

  function reset() {
    active.current?.controller.abort();
    active.current = null;
    setTurns([]);
    setDraft("");
    setBusy(false);
    setAnnouncement("New conversation started.");
    follow.current = true;
    input.current?.focus();
  }

  return (
    <div className={`portfolio${turns.length ? " has-conversation" : ""}`}>
      <a className="portfolio-skip" href="#chat-input">Skip to conversation</a>
      <header className="portfolio-header">
        <Link className="portfolio-brand" href="/" aria-label="Thibault Leveau, home" onClick={reset}>
          <BrandMark className="portfolio-logo" />
          <span>Thibault Leveau</span>
        </Link>
        <div className="portfolio-header-actions">
          {turns.length > 0 && <button type="button" className="new-conversation" onClick={reset} aria-label="New conversation"><span className="new-conversation-label">New conversation</span><Arrow diagonal /></button>}
          <ThemeToggle />
        </div>
      </header>

      <main className="chat-main" id="main-content">
        {turns.length === 0 ? (
          <section className="chat-welcome" aria-labelledby="chat-heading">
            <span className="welcome-mark" aria-hidden="true">✳</span>
            <p className="chat-eyebrow">GOOD TO MEET YOU</p>
            <h1 id="chat-heading">Hi, I’m Thibault.<br /><span>Let’s talk about my work.</span></h1>
            <p className="chat-introduction">Explore my experience, projects, and skills through a conversation.<br className="desktop-break" /> Ask a question, or pick a starting point below.</p>
            <div className="chat-prompts" aria-label="Suggested questions">
              {prompts.map((prompt) => (
                <button key={prompt.title} type="button" onClick={() => void send(prompt.question)}>
                  {prompt.title}<Arrow diagonal />
                </button>
              ))}
            </div>
          </section>
        ) : (
          <section className="chat-transcript" role="log" aria-label="Conversation" aria-live="off">
            <h1 className="sr-only">A conversation about my career</h1>
            {turns.map((turn, index) => (
              <article className="chat-turn" key={turn.id}>
                <div className="chat-question"><span className="sr-only">You: </span>{turn.question}</div>
                <div className="chat-answer">
                  <div className="answer-identity"><span className="answer-mark" aria-hidden="true">✳</span><span>Thibault’s assistant<small>AI</small></span></div>
                  {turn.answer && <div className="answer-content"><Answer text={turn.answer} /></div>}
                  {turn.status === "pending" && <p className="thinking"><span aria-hidden="true">• • •</span>{turn.answer ? "Still writing…" : "Thinking about your question…"}</p>}
                  {turn.status === "complete" && <SourceList sources={turn.sources} />}
                  {turn.status === "error" && <p className="chat-error" role="alert">{turn.error}</p>}
                  {turn.status === "stopped" && <p className="chat-stopped">Response stopped.</p>}
                  {(turn.status === "error" || turn.status === "stopped") && index === turns.length - 1 && !busy && (
                    <button type="button" className="retry-response" onClick={() => void send(turn.question, turn.id)}>Try again <span aria-hidden="true">↻</span></button>
                  )}
                </div>
              </article>
            ))}
            <div ref={bottom} />
          </section>
        )}

        <div className="composer-area">
          <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(draft); }}>
            <label className="sr-only" htmlFor="chat-input">Ask about my career</label>
            <textarea
              ref={input}
              id="chat-input"
              placeholder={turns.length ? "Ask a follow-up question…" : "What would you like to know about me?"}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void send(draft);
                }
              }}
              maxLength={4000}
              rows={2}
              aria-describedby={draft.length > 3500 ? "composer-count" : undefined}
            />
            <div className="composer-controls">
              {draft.length > 3500 && <span id="composer-count">{draft.length.toLocaleString()} / 4,000</span>}
              {busy ? (
                <button type="button" className="send-button stop-button" aria-label="Stop response" onClick={(event) => {
                  // This button becomes Send during the click; prevent its submit action.
                  event.preventDefault();
                  stop();
                }}><span aria-hidden="true" /></button>
              ) : (
                <button type="submit" className="send-button" aria-label="Send message" disabled={!draft.trim()}><Arrow /></button>
              )}
            </div>
          </form>
        </div>
      </main>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </div>
  );
}
