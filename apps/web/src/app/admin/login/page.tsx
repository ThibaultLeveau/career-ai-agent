import Link from "next/link";
import { LoginForm } from "@/components/admin/login";
import { Icon } from "@/components/admin/ui";
import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";

export default function LoginPage() {
  return (
    <main className="login-page">
      <div className="login-appearance"><ThemeToggle /></div>
      <Link href="/" className="login-brand" aria-label="Thibault Leveau, home">
        <span className="brand-mark">
          <BrandMark size={24} />
        </span>
        Thibault Leveau
        <span className="admin-label">Admin</span>
      </Link>
      <section className="login-card">
        <span className="login-lock">
          <Icon name="lock" size={23} />
        </span>
        <p className="eyebrow">ADMINISTRATION</p>
        <h1>Welcome back.</h1>
        <p>Sign in to your private workspace.</p>
        <LoginForm />
        <p className="login-footnote">
          Access is restricted to the portfolio administrator.
        </p>
      </section>
      <Link className="login-back" href="/">
        ← Back to portfolio
      </Link>
    </main>
  );
}
