import { chatActivityRows, type AgentActivity, type ChatActivity } from "@/lib/chat";

function ActivityIndicator({ state }: { state: AgentActivity["state"] }) {
  if (state === "running") return (
    <span className="activity-indicator activity-dots" role="img" aria-label="Running">
      <span /><span /><span />
    </span>
  );
  return (
    <svg className="activity-indicator" role="img" aria-label={state === "complete" ? "Complete" : "Unavailable"}
      width="18" height="18" viewBox="0 0 20 20" fill="none">
      <path d={state === "complete" ? "m4 10 4 4 8-8" : "M5 10h10"}
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ChatActivityView({ activity, writing }: { activity?: ChatActivity; writing: boolean }) {
  const rows = chatActivityRows(activity, writing);
  if (!rows.length) return null;
  return (
    <div className="thinking" data-stage={activity?.stage ?? (writing ? "answering" : "analyzing")}
      role="list" aria-label="Agent activity" aria-live="off">
      {rows.map((item) => (
        <div key={item.id} className="activity-row" data-activity-id={item.id} data-state={item.state} role="listitem">
          <ActivityIndicator state={item.state} />
          <div className="activity-copy">
            <strong>{item.agent}</strong>
            <span className="activity-separator" aria-hidden="true"> — </span>
            <span className="activity-message">{item.message}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
