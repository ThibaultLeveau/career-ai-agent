"use client";

export default function AdminError({ reset }: { reset: () => void }) {
  return (
    <div className="admin-content">
      <h1>Workspace unavailable</h1>
      <p>We could not reach the administration service. Please try again.</p>
      <button className="button" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
