/**
 * Renders the forgot-password screen where a user requests a reset link by email.
 * Submission swaps the form for an inline confirmation panel rather than navigating away,
 * and a dev skip button bypasses the absent v1 auth backend straight to the dashboard.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Eyebrow } from '@/components/ui/eyebrow';
import { SkipLoginButton } from '@/components/auth/SkipLoginButton';

/**
 * Foundry · Aurora forgot-password screen. Submits inline to a "Sent"
 * confirmation panel rather than navigating away (per design README
 * §"Forms · Forgot"). No real SMTP backend in v1; the dev bypass below
 * lands the user on /dashboard directly.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.includes('@')) return;
    setSent(true);
  };

  return (
    <main data-testid="page-forgot-password" className="w-full max-w-md">
      <div className="rounded-card border border-line/30 bg-bg-paper p-8 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_24px_rgba(0,0,0,0.4)]">
        <Eyebrow>Password reset</Eyebrow>
        <h2 className="mt-3 font-display text-3xl font-extrabold leading-tight tracking-tight text-fg">
          Forgot your password.
        </h2>
        <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
          Enter the email you signed up with. We'll send a one-time link to set a new one.
          Links expire in fifteen minutes.
        </p>

        {!sent ? (
          <form onSubmit={handleSubmit} className="mt-6 space-y-5" noValidate>
            <div className="space-y-2">
              <Label
                htmlFor="forgot-email"
                className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
              >
                Email
              </Label>
              <Input
                id="forgot-email"
                type="email"
                autoComplete="email"
                placeholder="you@school.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="forgot-email"
                className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
              />
            </div>
            <Button
              type="submit"
              size="lg"
              className="w-full"
              data-testid="forgot-submit"
            >
              Send reset link
            </Button>
            <p className="font-mono text-xs text-fg-subtle">
              Remembered it?{' '}
              <Link to="/signin" className="text-accent underline-offset-4 hover:underline">
                Back to sign in
              </Link>
              .
            </p>
          </form>
        ) : (
          <div
            data-testid="forgot-sent"
            className="mt-6 rounded-md border border-success/40 bg-success/5 px-4 py-4"
          >
            <Eyebrow className="text-success">Sent</Eyebrow>
            <h3 className="mt-2 font-display text-lg font-bold text-fg">
              Check your inbox.
            </h3>
            <p className="mt-2 font-mono text-sm leading-relaxed text-fg-muted">
              If <span className="text-fg">{email}</span> is on file, a reset link is on
              the way. It can take a minute. Check spam if it doesn't arrive.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSent(false)}
                data-testid="forgot-try-again"
              >
                Try a different address
              </Button>
              <Link to="/signin">
                <Button variant="ghost" size="sm">
                  Back to sign in
                </Button>
              </Link>
            </div>
          </div>
        )}

        <div className="mt-6 border-t border-line/30 pt-4">
          <p className="font-mono text-xs text-fg-subtle">
            No real auth backend in v1 — the dev bypass below lands you on the dashboard.
          </p>
          <SkipLoginButton
            label="Dev: Skip — go to dashboard"
            testId="dev-forgot-bypass"
            redirectTo="/dashboard"
          />
        </div>
      </div>
    </main>
  );
}
