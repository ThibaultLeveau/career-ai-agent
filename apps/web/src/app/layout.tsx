import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Career AI | Personal portfolio",
  description: "An AI-powered personal portfolio, under construction.",
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
