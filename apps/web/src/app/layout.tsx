import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Thibault Leveau | A career in conversation",
  description:
    "Get to know Thibault Leveau. Ask his AI career assistant about his experience, projects, and skills.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 antialiased">{children}</body>
    </html>
  );
}
