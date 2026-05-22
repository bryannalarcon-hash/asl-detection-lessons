import { useState } from 'react';
import { HelpCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ReferenceVideo } from './ReferenceVideo';

interface HintButtonProps {
  signSlug: string;
  englishGloss: string;
}

// Single hardcoded fallback hint per PRD §"What to skip vs do".
const FALLBACK_HINT = 'Try again — focus on the handshape, then trace the movement slowly.';

/**
 * Foundry · Aurora quiet "? Show a hint" trigger. Sits in the bordered hint
 * row between the media cells and the CTA row. Opens a dialog that contains
 * the hint text + the reference video at larger scale.
 */
export function HintButton({ signSlug, englishGloss }: HintButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        data-testid="hint-button"
        className="inline-flex h-8 items-center gap-2 rounded-md border border-transparent bg-transparent px-3 font-mono text-[0.78rem] text-fg-muted transition-[background-color,border-color,color] duration-150 ease-out hover:border-border hover:bg-bg-paper hover:text-fg focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2"
      >
        <HelpCircle className="h-4 w-4" />
        Show a hint
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Hint · {englishGloss}</DialogTitle>
          <DialogDescription>{FALLBACK_HINT}</DialogDescription>
        </DialogHeader>
        <div className="mt-4 h-64">
          <ReferenceVideo signSlug={signSlug} englishGloss={englishGloss} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
