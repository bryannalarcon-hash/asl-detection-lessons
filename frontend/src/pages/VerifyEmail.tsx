import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eyebrow } from '@/components/ui/eyebrow';
import { Button } from '@/components/ui/button';
import { SkipLoginButton } from '@/components/auth/SkipLoginButton';

/**
 * Foundry · Aurora email-verification screen.
 *
 * Six individual digit cells (mono, 1.4rem). Auto-focus next cell on input,
 * auto-back on backspace when the current cell is empty. When all six are
 * filled, wait 300ms then navigate to `/onboarding/welcome`.
 *
 * Backend doesn't issue real codes yet — this is a UX placeholder that
 * advances on completion. Any 6 digits will navigate. The dev bypass
 * remains available for tests that don't want to type.
 */
export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', '']);
  const [resent, setResent] = useState(false);
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const update = (i: number, raw: string) => {
    const value = raw.replace(/[^0-9]/g, '').slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[i] = value;
      if (value && i < 5) {
        // Defer focus so React commits the value before we move on.
        queueMicrotask(() => refs.current[i + 1]?.focus());
      }
      if (next.every((d) => d.length === 1)) {
        setTimeout(() => navigate('/onboarding/welcome'), 300);
      }
      return next;
    });
  };

  const onKeyDown = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) {
      refs.current[i - 1]?.focus();
    }
  };

  return (
    <main data-testid="page-verify-email" className="w-full max-w-md">
      <div className="rounded-card border border-line/30 bg-bg-paper p-8 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_24px_rgba(0,0,0,0.4)]">
        <Eyebrow>Verify email</Eyebrow>
        <h2 className="mt-3 font-display text-3xl font-extrabold leading-tight tracking-tight text-fg">
          One more step.
        </h2>
        <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
          We sent a six-digit code to your inbox. Enter it here, or click the link in the
          message — either works.
        </p>

        <div className="mt-6">
          <Eyebrow>Enter verification code</Eyebrow>
          <div className="mt-3 flex justify-between gap-2">
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                data-testid={`verify-code-${i}`}
                inputMode="numeric"
                maxLength={1}
                value={d}
                onChange={(e) => update(i, e.target.value)}
                onKeyDown={(e) => onKeyDown(i, e)}
                className="h-[60px] w-[48px] rounded-md border border-line/30 bg-bg-deep text-center font-mono text-[1.4rem] text-fg outline-none transition-[border-color,box-shadow,background-color] focus:border-accent focus:bg-bg-paper focus:ring-[3px] focus:ring-accent/20"
                aria-label={`Verification code digit ${i + 1}`}
              />
            ))}
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-xs text-fg-subtle">Didn't get the code?</span>
          <Button
            variant="link"
            size="sm"
            onClick={() => setResent(true)}
            data-testid="verify-resend"
          >
            {resent ? 'Resent ✓' : 'Resend'}
          </Button>
        </div>

        <p className="mt-6 font-mono text-xs text-fg-subtle">
          Wrong address?{' '}
          <Link to="/signup" className="text-accent underline-offset-4 hover:underline">
            Back to sign-up
          </Link>{' '}
          to change it.
        </p>

        <div className="mt-6 border-t border-line/30 pt-4">
          <p className="font-mono text-xs text-fg-subtle">
            No SMTP in v1. Use the dev bypass to skip verification.
          </p>
          <SkipLoginButton
            label="Dev: Mark verified"
            testId="dev-mark-verified"
            redirectTo="/onboarding/welcome"
          />
        </div>
      </div>
    </main>
  );
}
