"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { PublicHeader } from "@/components/public-header";
import { ChatAnswer } from "@/components/chat-answer";
import { ChatActivityView } from "@/components/chat-activity";
import { ChatComponentView } from "@/components/chat-components";
import type { ChatComponent, DetailAction } from "@/lib/chat-components";
import "./chat-workspace.css";
import {
  completedHistory,
  completedResumeState,
  chatActivityAnnouncement,
  readChatStream,
  type ChatSource,
  type ChatTurn,
} from "@/lib/chat";

const desktopQuery = "(min-width: 1024px)";
function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(desktopQuery);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
function desktopSnapshot() { return window.matchMedia(desktopQuery).matches; }
function serverDesktopSnapshot() { return false; }
function hasResults(turn: ChatTurn) {
  return turn.blocks.some((block) => block.type === "component" && block.component.type !== "resume_download");
}

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
  const [selectedResultsTurnId, setSelectedResultsTurnId] = useState<number | null>(null);
  const desktop = useSyncExternalStore(subscribeDesktop, desktopSnapshot, serverDesktopSnapshot);
  const resultTurns = turns.filter(hasResults);
  const selectedResults = resultTurns.find((turn) => turn.id === selectedResultsTurnId) ?? resultTurns.at(-1);
  const resultsAvailable = Boolean(selectedResults);
  const transcript = useRef<HTMLElement>(null);
  const resultsBody = useRef<HTMLDivElement>(null);
  const resultsHeading = useRef<HTMLHeadingElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);
  const active = useRef<{ id: number; controller: AbortController } | null>(null);
  const follow = useRef(true);

  useEffect(() => {
    function onScroll() {
      if (!window.matchMedia(desktopQuery).matches)
        follow.current = document.documentElement.scrollHeight - window.innerHeight - window.scrollY < 180;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      active.current?.controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!turns.length || !follow.current) return;
    if (desktop && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight;
    else bottom.current?.scrollIntoView({ block: "end" });
  }, [turns, desktop]);

  useEffect(() => {
    if (resultsBody.current) resultsBody.current.scrollTop = 0;
  }, [selectedResults?.id, desktop]);

  useEffect(() => {
    if (!input.current) return;
    input.current.style.height = "auto";
    input.current.style.height = `${Math.min(input.current.scrollHeight, 160)}px`;
  }, [draft, desktop, resultsAvailable]);

  function updateTurn(id: number, update: Partial<ChatTurn> | ((turn: ChatTurn) => Partial<ChatTurn>)) {
    setTurns((current) => current.map((turn) => turn.id === id
      ? { ...turn, ...(typeof update === "function" ? update(turn) : update) }
      : turn));
  }

  async function send(question: string, retryId?: number, action?: DetailAction) {
    const message = question.trim();
    if (!message || active.current) return;
    const id = retryId ?? ++nextId.current;
    const previous = retryId === undefined ? turns : turns.filter((turn) => turn.id !== retryId);
    const history = completedHistory(previous);
    const resumeState = completedResumeState(previous);
    while (history.length && new TextEncoder().encode(JSON.stringify({ message, history, action, ...resumeState })).byteLength > 65536)
      history.splice(0, 2);
    const request = { id, controller: new AbortController() };
    active.current = request;
    follow.current = true;
    const turn: ChatTurn = { id, question: message, answer: "", blocks: [], action, status: "pending", sources: [] };
    setTurns([...previous, turn]);
    setSelectedResultsTurnId(null);
    setDraft("");
    setBusy(true);
    setAnnouncement(chatActivityAnnouncement());
    input.current?.focus();
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history, ...(action ? { action } : {}), ...resumeState }),
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
        if (active.current === request) {
          updateTurn(id, (current) => {
            const blocks = [...current.blocks];
            const last = blocks.at(-1);
            if (last?.type === "text") blocks[blocks.length - 1] = { type: "text", text: last.text + text };
            else blocks.push({ type: "text", text });
            return { answer: current.answer + text, blocks, activity: undefined };
          });
          setAnnouncement(chatActivityAnnouncement(undefined, true));
        }
      }, (activity) => {
        if (active.current === request) {
          updateTurn(id, { activity });
          setAnnouncement(chatActivityAnnouncement(activity));
        }
      }, (component) => {
        if (active.current === request) {
          updateTurn(id, (current) => ({
            answer: `${current.answer}\n\n${component.introduction}`.trim(),
            blocks: [...current.blocks, { type: "component", ...component }],
            activity: undefined,
          }));
          setAnnouncement(chatActivityAnnouncement(undefined, true));
        }
      }, () => {
        if (active.current === request) updateTurn(id, { resumeClarificationAsked: true });
      });
      if (active.current !== request) return;
      updateTurn(id, { status: "complete", sources, activity: undefined });
      setAnnouncement("Response ready. You can read it in the conversation.");
    } catch (error) {
      if (active.current !== request) return;
      const message = error instanceof Error && error.name !== "TypeError" && error.name !== "SyntaxError"
        ? error.message
        : "The connection was interrupted. Please try again.";
      updateTurn(id, { status: "error", error: message, activity: undefined });
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
    updateTurn(request.id, { status: "stopped", activity: undefined });
    setBusy(false);
    setAnnouncement("Response stopped.");
    input.current?.focus();
  }

  function reset() {
    active.current?.controller.abort();
    active.current = null;
    setTurns([]);
    setSelectedResultsTurnId(null);
    setDraft("");
    setBusy(false);
    setAnnouncement("New conversation started.");
    follow.current = true;
    input.current?.focus();
  }

  function componentView(turn: ChatTurn, blockIndex: number, component: ChatComponent) {
    return <ChatComponentView data={component} busy={busy}
      onOpen={(question, action) => void send(question, undefined, action)}
      onUpdate={(data) => {
        if (!desktop) follow.current = false;
        updateTurn(turn.id, (current) => ({
          blocks: current.blocks.map((item, index) => index === blockIndex && item.type === "component"
            ? { ...item, component: data } : item),
        }));
      }} />;
  }

  function showResults(id: number) {
    setSelectedResultsTurnId(id);
    requestAnimationFrame(() => resultsHeading.current?.focus({ preventScroll: true }));
  }

  return (
    <div className={`portfolio career-chat-page${turns.length ? " has-conversation" : ""}${selectedResults ? " has-results" : ""}`}>
      <a className="portfolio-skip" href="#chat-input">Skip to conversation</a>
      <PublicHeader onHomeClick={reset} actions={turns.length > 0 && <button type="button" className="new-conversation" onClick={reset} aria-label="New conversation"><span className="new-conversation-label">New conversation</span><Arrow diagonal /></button>} />

      <main className="chat-main chat-workspace" id="main-content">
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
          <section className="chat-transcript" ref={transcript} role="log" aria-label="Conversation" aria-live="off"
            tabIndex={desktop ? 0 : undefined}
            onScroll={(event) => {
              if (!desktop) return;
              const element = event.currentTarget;
              follow.current = element.scrollHeight - element.clientHeight - element.scrollTop < 120;
            }}>
            <h1 className="sr-only">A conversation about my career</h1>
            {turns.map((turn, index) => (
              <article className="chat-turn" key={turn.id} data-turn-id={turn.id}>
                <div className="chat-question"><span className="sr-only">You: </span>{turn.question}</div>
                <div className="chat-answer">
                  <div className="answer-identity"><span className="answer-mark" aria-hidden="true">✳</span><span>Thibault’s assistant<small>AI</small></span></div>
                  {turn.status === "pending" && <ChatActivityView activity={turn.activity} writing={turn.blocks.length > 0} />}
                  {turn.blocks.map((block, blockIndex) => block.type === "text"
                    ? <div className="answer-content" key={blockIndex}><ChatAnswer text={block.text} /></div>
                    : <div className={`answer-component${block.component.type === "resume_download" ? " answer-resume" : ""}`} key={blockIndex} data-block-index={blockIndex}>
                      <div className="answer-content"><ChatAnswer text={block.introduction} /></div>
                      {(!desktop || block.component.type === "resume_download") && componentView(turn, blockIndex, block.component)}
                    </div>)}
                  {desktop && hasResults(turn) && <button type="button" className="view-results" aria-controls="chat-results"
                    aria-pressed={selectedResults?.id === turn.id} onClick={() => showResults(turn.id)}>
                    View results <span aria-hidden="true">↗</span>
                  </button>}
                  {turn.status === "complete" && <SourceList sources={turn.sources} />}
                  {turn.status === "error" && <p className="chat-error" role="alert">{turn.error}</p>}
                  {turn.status === "stopped" && <p className="chat-stopped">Response stopped.</p>}
                  {(turn.status === "error" || turn.status === "stopped") && index === turns.length - 1 && !busy && (
                    <button type="button" className="retry-response" onClick={() => void send(turn.question, turn.id, turn.action)}>Try again <span aria-hidden="true">↻</span></button>
                  )}
                </div>
              </article>
            ))}
            <div ref={bottom} />
          </section>
        )}

        {desktop && selectedResults && <aside className="chat-results" id="chat-results" aria-labelledby="chat-results-heading" data-turn-id={selectedResults.id}>
          <header className="chat-results-header">
            <div className="chat-results-title"><h2 id="chat-results-heading" ref={resultsHeading} tabIndex={-1}>Related work</h2>
              {resultTurns.length > 1 && <button type="button" className="latest-results" disabled={selectedResultsTurnId === null}
                onClick={() => setSelectedResultsTurnId(null)}>Latest results</button>}
            </div>
            {resultTurns.length > 1 && <label className="chat-results-select">Results for
              <select value={selectedResults.id} onChange={(event) => setSelectedResultsTurnId(Number(event.target.value))}>
                {[...resultTurns].reverse().map((turn) => <option key={turn.id} value={turn.id}>{turn.question}</option>)}
              </select>
            </label>}
            <p className="chat-results-question">{selectedResults.question}</p>
          </header>
          <div className="chat-results-body" ref={resultsBody} tabIndex={0} role="region" aria-label="Selected results">
            {selectedResults.blocks.map((block, blockIndex) => block.type === "component" && block.component.type !== "resume_download"
              ? <div className="chat-result-component" key={`${selectedResults.id}-${blockIndex}`} data-block-index={blockIndex}>
                {componentView(selectedResults, blockIndex, block.component)}
              </div> : null)}
          </div>
        </aside>}

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
              rows={1}
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
