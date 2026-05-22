import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { AuthShell } from '@/components/layout/AuthShell';

import LandingPage from '@/pages/Landing';
import SignUpPage from '@/pages/SignUp';
import SignInPage from '@/pages/SignIn';
import ForgotPasswordPage from '@/pages/ForgotPassword';
import VerifyEmailPage from '@/pages/VerifyEmail';
import OnboardingWelcomePage from '@/pages/OnboardingWelcome';
import OnboardingCameraPage from '@/pages/OnboardingCamera';
import OnboardingCalibrationPage from '@/pages/OnboardingCalibration';
import FirstSignTutorialPage from '@/pages/FirstSignTutorial';
import DashboardPage from '@/pages/Dashboard';
import LessonCatalogPage from '@/pages/LessonCatalog';
import LessonIntroPage from '@/pages/LessonIntro';
import PracticePage from '@/pages/Practice';
import LessonCompletePage from '@/pages/LessonComplete';
import AccountSettingsPage from '@/pages/AccountSettings';
import AppSettingsPage from '@/pages/AppSettings';
import NotificationSettingsPage from '@/pages/NotificationSettings';
import PrivacyPage from '@/pages/Privacy';
import HelpPage from '@/pages/Help';
import AboutPage from '@/pages/About';
import CameraDeniedPage from '@/pages/CameraDenied';
import OfflinePage from '@/pages/Offline';
import NotFoundPage from '@/pages/NotFound';

export const router = createBrowserRouter([
  // Pages with no top nav (public/landing + auth)
  {
    element: <AuthShell />,
    children: [
      { path: '/signup', element: <SignUpPage /> },
      { path: '/signin', element: <SignInPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
    ],
  },
  // Landing is its own page (no shell)
  { path: '/', element: <LandingPage /> },

  // Onboarding flows — keep them shell-less so the first-run feels focused
  { path: '/onboarding/welcome', element: <OnboardingWelcomePage /> },
  { path: '/onboarding/camera', element: <OnboardingCameraPage /> },
  { path: '/onboarding/calibration', element: <OnboardingCalibrationPage /> },
  { path: '/onboarding/first-sign', element: <FirstSignTutorialPage /> },

  // Practice screen owns its own 56px header and is full-bleed — keep it
  // out of the AppShell so the global nav doesn't compete for focus.
  { path: '/lessons/:slug/practice', element: <PracticePage /> },

  // App shell (authenticated learner surfaces)
  {
    element: <AppShell />,
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/lessons', element: <LessonCatalogPage /> },
      { path: '/lessons/:slug', element: <LessonIntroPage /> },
      { path: '/lessons/:slug/complete', element: <LessonCompletePage /> },
      { path: '/settings/account', element: <AccountSettingsPage /> },
      { path: '/settings/app', element: <AppSettingsPage /> },
      { path: '/settings/notifications', element: <NotificationSettingsPage /> },
      { path: '/privacy', element: <PrivacyPage /> },
      { path: '/help', element: <HelpPage /> },
      { path: '/about', element: <AboutPage /> },
      { path: '/errors/camera-denied', element: <CameraDeniedPage /> },
      { path: '/errors/offline', element: <OfflinePage /> },
    ],
  },

  { path: '*', element: <NotFoundPage /> },
]);
