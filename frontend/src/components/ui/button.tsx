import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Foundry · Aurora button variants.
// Visual contract is documented in design/extracted/design_handoff_asl_pilot/README.md.
// - `default` (primary): cyan→violet gradient fill, dark navy text, sheen + drop shadow.
// - `secondary`: paper surface, hairline border, accent-soft border on hover.
// - `outline`: transparent fill, 1px accent border, accent-tinted bg on hover.
// - `ghost`: transparent, surface brighten on hover.
// - `destructive`: error-red filled button, same shape language as primary.
// - `link`: text-only accent link.
// Sizes: xs / sm / default / lg / icon (+ icon-xs, icon-sm, icon-lg) preserved;
// new `pill` size for the primary CTAs (`h-11 px-6 rounded-full`).
const buttonVariants = cva(
  // Base: enumerated transitions (no `transition-all`), 1px-press on active,
  // accent focus ring per Foundry · Aurora.
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap select-none transition-[background-color,border-color,box-shadow,color,filter,transform] duration-150 ease-out motion-reduce:transition-none outline-none focus-visible:outline-2 focus-visible:outline-accent-ring focus-visible:outline-offset-2 active:translate-y-px active:duration-75 disabled:pointer-events-none disabled:opacity-40 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // Primary: gradient fill, dark navy text, inset sheen + drop shadow, brightness on hover.
        // Background, color, and shadow come from the `.btn-aurora-primary` utility
        // class authored alongside the tokens (tokens-coder owns the CSS).
        default:
          "btn-aurora-primary border-0 font-semibold hover:[filter:brightness(1.08)]",
        // Outline: hairline accent border + accent-tinted hover fill.
        outline:
          "border-accent/60 bg-transparent text-fg hover:bg-accent/12 hover:border-accent",
        // Secondary: paper surface, accent-soft border on hover.
        secondary:
          "bg-bg-paper border border-line text-fg hover:bg-bg-elev hover:border-accent-soft",
        // Ghost: transparent → surface brighten on hover, no border.
        ghost:
          "text-fg-muted hover:bg-bg-elev hover:text-fg aria-expanded:bg-bg-elev aria-expanded:text-fg",
        // Destructive: error-red filled button, same shape language as primary.
        destructive:
          "border-0 font-semibold text-[#08101c] bg-[hsl(var(--error))] shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_8px_24px_rgba(0,0,0,0.4)] hover:[filter:brightness(1.08)] focus-visible:outline-[hsl(var(--error))]",
        link: "text-accent underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        // Pill: tall, rounded-full primary CTA from the Foundry · Aurora design.
        pill: "h-11 gap-2 px-6 rounded-full text-sm has-data-[icon=inline-end]:pr-5 has-data-[icon=inline-start]:pl-5",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
