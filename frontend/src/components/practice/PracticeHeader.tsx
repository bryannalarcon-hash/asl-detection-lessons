/**
 * Sticky header bar for the practice screen showing the lesson back link and
 * sign counter alongside controls to step back a drill or sign, toggle the
 * camera, pause, and exit. It exposes these actions through callbacks supplied
 * by the practice screen.
 */
import { ChevronLeft, Pause, X as XIcon, Undo2, CornerUpLeft, Video, VideoOff } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface PracticeHeaderProps {
  lessonTitle: string;
  lessonSlug: string;
  signIndex: number;
  signTotal: number;
  canBackDrill: boolean;
  canBackSign: boolean;
  cameraOn: boolean;
  onBackDrill: () => void;
  onBackSign: () => void;
  onToggleCamera: () => void;
  onPause: () => void;
  onExit: () => void;
}

/**
 * Foundry · Aurora practice header. 56px sticky bar with the lesson back link,
 * sign counter, back-drill / back-sign affordances, camera toggle, pause and
 * exit ghost buttons.
 *
 * Per the design README §"Hero screen detail — Practice", the header is
 * `bg: hsl(var(--bg) / 0.85); backdrop-filter: blur(8px); border-bottom:
 * 1px solid hsl(var(--line))`.
 */
export function PracticeHeader({
  lessonTitle,
  lessonSlug,
  signIndex,
  signTotal,
  canBackDrill,
  canBackSign,
  cameraOn,
  onBackDrill,
  onBackSign,
  onToggleCamera,
  onPause,
  onExit,
}: PracticeHeaderProps) {
  return (
    <header
      data-testid="practice-header"
      className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-[hsl(var(--bg)/0.85)] px-4 backdrop-blur-md md:gap-4 md:px-6"
    >
      <Link
        to={`/lessons/${lessonSlug}`}
        data-testid="practice-back-lesson"
        className="inline-flex min-w-0 items-center gap-1.5 font-mono text-[0.86rem] text-fg-muted transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
        aria-label={`Back to ${lessonTitle} lesson intro`}
      >
        <ChevronLeft className="h-4 w-4 flex-none" />
        <span className="truncate">
          <span className="hidden sm:inline">Lesson · </span>
          <span className="text-fg">{lessonTitle}</span>
        </span>
      </Link>

      <div className="ml-auto flex flex-none items-center gap-1 text-fg-muted md:flex-wrap md:gap-2">
        <span
          data-testid="practice-progress"
          className="px-1 font-mono text-[0.78rem] text-fg"
        >
          <span className="hidden sm:inline">Sign </span>
          {signIndex + 1}
          <span className="hidden sm:inline"> of</span>
          <span className="sm:hidden">/</span> {signTotal}
        </span>

        <HeaderButton
          data-testid="practice-back-drill"
          disabled={!canBackDrill}
          onClick={onBackDrill}
          title="Back one drill"
          aria-label="Back one drill"
        >
          <Undo2 className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Back drill</span>
        </HeaderButton>

        <HeaderButton
          data-testid="practice-back-sign"
          disabled={!canBackSign}
          onClick={onBackSign}
          title="Back one sign"
          aria-label="Back one sign"
        >
          <CornerUpLeft className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Back sign</span>
        </HeaderButton>

        <span aria-hidden="true" className="mx-1 hidden h-4 w-px bg-border md:inline-block" />

        <HeaderButton
          data-testid="practice-camera-toggle"
          data-state={cameraOn ? 'on' : 'off'}
          onClick={onToggleCamera}
          title={cameraOn ? 'Turn camera off' : 'Turn camera on'}
          aria-label={cameraOn ? 'Turn camera off' : 'Turn camera on'}
        >
          {cameraOn ? <Video className="h-3.5 w-3.5" /> : <VideoOff className="h-3.5 w-3.5" />}
          <span className="hidden md:inline">{cameraOn ? 'Camera on' : 'Camera off'}</span>
        </HeaderButton>

        <HeaderButton
          data-testid="practice-pause"
          onClick={onPause}
          title="Pause practice"
          aria-label="Pause practice"
        >
          <Pause className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Pause</span>
        </HeaderButton>

        <HeaderButton
          data-testid="practice-exit"
          onClick={onExit}
          title="Exit to lessons"
          aria-label="Exit to lessons"
        >
          <XIcon className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Exit</span>
        </HeaderButton>
      </div>
    </header>
  );
}

interface HeaderButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

function HeaderButton({ className, children, ...props }: HeaderButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 font-mono text-[0.78rem] text-fg-muted',
        'transition-[background-color,color,transform] duration-150 ease-out',
        'hover:bg-bg-elev hover:text-fg',
        'active:translate-y-px',
        'focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2',
        'disabled:pointer-events-none disabled:opacity-40',
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
