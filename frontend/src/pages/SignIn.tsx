import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Eyebrow } from '@/components/ui/eyebrow';
import { SkipLoginButton } from '@/components/auth/SkipLoginButton';
import { useSignIn } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import { isDevToolsEnabled } from '@/lib/env';
import { DEV_EMAIL, DEV_PASSWORD } from '@/lib/dev-credentials';

const schema = z.object({
  email: z.string().email('Enter a valid email.'),
  password: z.string().min(8, 'At least 8 characters.'),
});

type FormValues = z.infer<typeof schema>;

/**
 * Foundry · Aurora sign-in. Bordered card on dark-paper background, with an
 * eyebrow ("RETURNING LEARNER") above a display heading and a mono lede.
 * Inputs sit on `--bg-deep` with a 1px line; focus brings a cyan border +
 * 3px accent-bg ring (defined on the Input primitive).
 */
export default function SignInPage() {
  const navigate = useNavigate();
  const signIn = useSignIn();
  const [formError, setFormError] = useState<string | null>(null);

  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await signIn.mutateAsync({ email: values.email, password: values.password });
      navigate('/dashboard');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setFormError('Invalid email or password.');
      } else {
        setFormError('Something went wrong. Try again.');
      }
    }
  };

  return (
    <main data-testid="page-sign-in" className="w-full max-w-md">
      <div className="rounded-card border border-line/30 bg-bg-paper p-8 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_24px_rgba(0,0,0,0.4)]">
        <Eyebrow>Returning learner</Eyebrow>
        <h2 className="mt-3 font-display text-3xl font-extrabold leading-tight tracking-tight text-fg">
          Welcome back.
        </h2>
        <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
          Pick up where you left off. New here?{' '}
          <Link to="/signup" className="text-accent underline-offset-4 hover:underline">
            Create an account
          </Link>
          .
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5" noValidate>
          <div className="space-y-2">
            <Label
              htmlFor="email"
              className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
            >
              Email
            </Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@school.edu"
              data-testid="sign-in-email"
              className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
              {...register('email')}
            />
            {formState.errors.email && (
              <p className="font-mono text-xs text-error">{formState.errors.email.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label
                htmlFor="password"
                className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
              >
                Password
              </Label>
              <Link
                to="/forgot-password"
                className="font-mono text-xs text-accent hover:underline"
                data-testid="forgot-password-link"
              >
                Forgot?
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              data-testid="sign-in-password"
              className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
              {...register('password')}
            />
            {formState.errors.password && (
              <p className="font-mono text-xs text-error">
                {formState.errors.password.message}
              </p>
            )}
          </div>

          {formError && (
            <p
              role="alert"
              data-testid="sign-in-error"
              className="rounded-md border border-error/40 bg-error/10 px-3 py-2 font-mono text-sm text-error"
            >
              {formError}
            </p>
          )}

          <Button
            type="submit"
            data-testid="sign-in-submit"
            className="w-full"
            size="lg"
            disabled={formState.isSubmitting || signIn.isPending}
          >
            {signIn.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        {isDevToolsEnabled() && (
          <div
            data-testid="sign-in-dev-hint"
            data-dev-override
            className="mt-6 rounded-md border border-warning/40 bg-warning/5 px-4 py-3"
          >
            <Eyebrow className="text-warning">Dev account</Eyebrow>
            <p className="mt-2 font-mono text-xs leading-relaxed text-fg-muted">
              <code className="font-mono text-fg">{DEV_EMAIL}</code>
              <br />
              <code className="font-mono text-fg">{DEV_PASSWORD}</code>
            </p>
          </div>
        )}

        <div className="mt-6 border-t border-line/30 pt-4">
          <p className="font-mono text-xs text-fg-subtle">
            Skip-login drops you in as the seeded dev user without typing a password.
          </p>
          <SkipLoginButton />
        </div>
      </div>
    </main>
  );
}
