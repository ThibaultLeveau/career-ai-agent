"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./ui";

const sections = [
  { href: "/admin/settings", label: "Account & security", icon: "lock" },
  { href: "/admin/settings/ai", label: "AI", icon: "spark" },
  { href: "/admin/settings/rag", label: "RAG", icon: "documents" },
] as const;

export function SettingsNavigation() {
  const pathname = usePathname();
  return (
    <aside className="settings-sidebar">
      <nav aria-label="Settings navigation">
        <p className="nav-label">SETTINGS</p>
        {sections.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`nav-item ${pathname === href ? "active" : ""}`}
            aria-current={pathname === href ? "page" : undefined}
          >
            <Icon name={icon} />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
