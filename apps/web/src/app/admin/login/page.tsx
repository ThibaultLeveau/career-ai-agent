import Link from "next/link";
import { LoginForm } from "@/components/admin/login";
import { Icon } from "@/components/admin/ui";

export default function LoginPage() {
  return (
    <main className="login-page">
      <Link href="/" className="login-brand">
        <span className="brand-mark">
          <Icon name="spark" />
        </span>
        Career AI
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
