"use client";

import Link from "next/link";
import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState, type RefObject } from "react";

export type MenuAction = {
  label: string;
  href?: string;
  download?: boolean;
  onSelect?: () => void;
  disabled?: boolean;
  danger?: boolean;
};

export function ActionMenu({
  label,
  actions,
  target,
}: {
  label: string;
  actions: MenuAction[];
  target?: RefObject<HTMLDivElement | null>;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  function open(x?: number, y?: number) {
    const rect = trigger.current!.getBoundingClientRect();
    setPoint({ x: x ?? rect.right - 188, y: y ?? rect.bottom + 4 });
  }
  function close(restore = true) {
    setPoint(null);
    if (restore) trigger.current?.focus({ preventScroll: true });
  }
  useEffect(() => {
    const row = target?.current;
    if (!row) return;
    const context = (event: MouseEvent) => {
      if ((event.target as Element).closest("input, textarea, select")) return;
      event.preventDefault();
      open(event.clientX, event.clientY);
    };
    const keyboard = (event: KeyboardEvent) => {
      if (
        event.key === "ContextMenu" ||
        (event.shiftKey && event.key === "F10")
      ) {
        event.preventDefault();
        open();
      }
    };
    row.addEventListener("contextmenu", context);
    row.addEventListener("keydown", keyboard);
    return () => {
      row.removeEventListener("contextmenu", context);
      row.removeEventListener("keydown", keyboard);
    };
  }, [target]);
  useEffect(() => {
    if (!point || !menu.current) return;
    const popup = menu.current;
    const rect = popup.getBoundingClientRect();
    popup.style.left = `${Math.max(8, Math.min(point.x, innerWidth - rect.width - 8))}px`;
    popup.style.top = `${Math.max(8, Math.min(point.y, innerHeight - rect.height - 8))}px`;
    (
      popup.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)') ??
      popup
    ).focus({ preventScroll: true });
    const outside = (event: PointerEvent) => {
      if (
        !popup.contains(event.target as Node) &&
        !trigger.current?.contains(event.target as Node)
      )
        setPoint(null);
    };
    const dismiss = () => setPoint(null);
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", dismiss);
    window.addEventListener("scroll", dismiss, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("scroll", dismiss, true);
    };
  }, [point]);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="icon-button row-menu-trigger"
        aria-label={`Actions for ${label}`}
        aria-haspopup="menu"
        aria-expanded={!!point}
        aria-controls={point ? id : undefined}
        onClick={() => (point ? close() : open())}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault();
            open();
          }
        }}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <circle cx="12" cy="5" r="1.7" />
          <circle cx="12" cy="12" r="1.7" />
          <circle cx="12" cy="19" r="1.7" />
        </svg>
      </button>
      {point &&
        createPortal(
          <div
            id={id}
            ref={menu}
            className="record-menu"
            role="menu"
            tabIndex={-1}
            aria-label={`Actions for ${label}`}
            style={{ left: point.x, top: point.y }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                close();
              }
              if (event.key === "Tab") close();
              const items = Array.from(
                menu.current!.querySelectorAll<HTMLElement>(
                  '[role="menuitem"]:not(:disabled)',
                ),
              );
              const index = items.indexOf(
                document.activeElement as HTMLElement,
              );
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? items.length - 1
                    : event.key === "ArrowDown"
                      ? (index + 1) % items.length
                      : event.key === "ArrowUp"
                        ? (index - 1 + items.length) % items.length
                        : -1;
              if (next >= 0) {
                event.preventDefault();
                items[next]?.focus();
              }
            }}
          >
            {actions.map((action) =>
              action.href ? (
                action.download ? (
                  <a
                    key={action.label}
                    role="menuitem"
                    href={action.href}
                    download
                    onClick={() => close()}
                  >
                    {action.label}
                  </a>
                ) : (
                  <Link
                    key={action.label}
                    role="menuitem"
                    href={action.href}
                    onClick={() => close()}
                  >
                    {action.label}
                  </Link>
                )
              ) : (
                <button
                  key={action.label}
                  type="button"
                  role="menuitem"
                  className={action.danger ? "menu-danger" : undefined}
                  disabled={action.disabled}
                  onClick={() => {
                    close();
                    action.onSelect?.();
                  }}
                >
                  {action.label}
                </button>
              ),
            )}
          </div>,
          document.querySelector(".admin") ?? document.body,
        )}
    </>
  );
}
