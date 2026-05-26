/**
 * Renders the account-creation screen with a zod-validated form (display name, email,
 * password with confirmation) that registers via useSignUp and routes into onboarding.
 * It preloads the in-browser CV engine while the user types and offers a dev skip-sign-up shortcut.
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Eyebrow } from '@/components/ui/eyebrow';
import { SkipLoginButton } from '@/components/auth/SkipLoginButton';
import { useSignUp } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import { preloadCaptureRep } from '@/cv/captureRep';

const schema = z
  .object({
    email: z.string().email('Enter a valid email.'),
    password: z.string().min(8, 'At least 8 characters.'),
    confirmPassword: z.string().min(1, 'Confirm your password.'),
    displayName: z
      .string()
      .min(1, 'Tell us what to call you.')
      .max(80, 'Display name must be 80 characters or fewer.'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match.',
  });

type FormValues = z.infer<typeof schema>;

/**
 * Foundry · Aurora sign-up. Same auth-card pattern as SignIn — eyebrow
 * "NEW LEARNER" + display headline + mono lede, bordered inputs on the
 * deep-well background, gradient primary submit.
 */
export default function SignUpPage() {
  const navigate = useNavigate();
  const signUp = useSignUp();
  const [formError, setFormError] = useState<string | null>(null);

  // Warm the in-browser CV engine (worker + ONNX nets) while the learner signs
  // up, so the lesson's Record button is ready with no cold-start. The worker
  // is a session singleton kept loaded across navigation.
  useEffect(() => {
    void preloadCaptureRep();
  }, []);

  const { register, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '', confirmPassword: '', displayName: '' },
  });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await signUp.mutateAsync({
        email: values.email,
        password: values.password,
        displayName: values.displayName,
      });
      navigate('/onboarding/welcome');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFormError('An account with that email already exists. Sign in instead?');
      } else {
        setFormError('Something went wrong. Try again.');
      }
    }
  };

  return (
    <main data-testid="page-sign-up" className="w-full max-w-md">
      <div className="rounded-card border border-line/30 bg-bg-paper p-8 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_8px_24px_rgba(0,0,0,0.4)]">
        <Eyebrow>New learner</Eyebrow>
        <h2 className="mt-3 font-display text-3xl font-extrabold leading-tight tracking-tight text-fg">
          Begin the pilot.
        </h2>
        <p className="mt-3 font-mono text-sm leading-relaxed text-fg-muted">
          Free for the pilot cohort. We'll send a verification email, then a short
          calibration. Already have an account?{' '}
          <Link to="/signin" className="text-accent underline-offset-4 hover:underline">
            Sign in
          </Link>
          .
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5" noValidate>
          <div className="space-y-2">
            <Label
              htmlFor="displayName"
              className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
            >
              Display name
            </Label>
            <Input
              id="displayName"
              type="text"
              autoComplete="name"
              placeholder="Alex"
              data-testid="sign-up-display-name"
              className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
              {...register('displayName')}
            />
            {formState.errors.displayName && (
              <p className="font-mono text-xs text-error">
                {formState.errors.displayName.message}
              </p>
            )}
          </div>

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
              data-testid="sign-up-email"
              className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
              {...register('email')}
            />
            {formState.errors.email && (
              <p className="font-mono text-xs text-error">{formState.errors.email.message}</p>
            )}
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label
                htmlFor="password"
                className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
              >
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                data-testid="sign-up-password"
                className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
                {...register('password')}
              />
              {formState.errors.password && (
                <p className="font-mono text-xs text-error">
                  {formState.errors.password.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label
                htmlFor="confirmPassword"
                className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-fg-muted"
              >
                Confirm
              </Label>
              <Input
                id="confirmPassword"
                type="password"
                autoComplete="new-password"
                data-testid="sign-up-confirm"
                className="h-11 bg-bg-deep focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
                {...register('confirmPassword')}
              />
              {formState.errors.confirmPassword && (
                <p className="font-mono text-xs text-error">
                  {formState.errors.confirmPassword.message}
                </p>
              )}
            </div>
          </div>

          {formError && (
            <p
              role="alert"
              data-testid="sign-up-error"
              className="rounded-md border border-error/40 bg-error/10 px-3 py-2 font-mono text-sm text-error"
            >
              {formError}
            </p>
          )}

          <Button
            type="submit"
            data-testid="sign-up-submit"
            className="w-full"
            size="lg"
            disabled={formState.isSubmitting || signUp.isPending}
          >
            {signUp.isPending ? 'Creating account…' : 'Create account'}
          </Button>
        </form>

        <div className="mt-6 border-t border-line/30 pt-4">
          <p className="font-mono text-xs text-fg-subtle">
            In a hurry? Skip account creation and drop in as the seeded dev user.
          </p>
          <SkipLoginButton
            label="Dev: Skip sign-up"
            testId="dev-skip-signup"
            redirectTo="/onboarding/welcome"
          />
        </div>
      </div>
    </main>
  );
}
