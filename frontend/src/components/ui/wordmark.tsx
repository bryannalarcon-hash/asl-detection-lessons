import { cn } from '@/lib/utils';

// Foundry · Aurora striped-stencil wordmark.
// The horizontal-stripe effect is delivered by the `.wordmark-stripe`
// utility class (repeating-linear-gradient background-clipped to text)
// and the `.font-wordmark` utility class (Archivo Black) — both owned
// by the tokens layer. Default text is "ASL PILOT" per the new brand.
interface WordmarkProps {
  text?: string;
  className?: string;
}

export function Wordmark({ text = 'ASL PILOT', className }: WordmarkProps) {
  return (
    <span
      data-testid="wordmark"
      className={cn(
        'font-wordmark wordmark-stripe text-2xl uppercase tracking-[0.04em] inline-block',
        className,
      )}
      aria-label={text}
    >
      {text}
    </span>
  );
}
