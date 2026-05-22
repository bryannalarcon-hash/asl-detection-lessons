import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Foundry · Aurora tokens — see frontend/src/styles/globals.css
        bg: {
          DEFAULT: 'hsl(var(--bg))',
          paper: 'hsl(var(--bg-paper))',
          elev: 'hsl(var(--bg-elev))',
          deep: 'hsl(var(--bg-deep))',
          // Back-compat aliases (old names still in use across components)
          elevated: 'hsl(var(--bg-elevated))',
          raised: 'hsl(var(--bg-raised))',
          deepest: 'hsl(var(--bg-deepest))',
        },
        fg: {
          DEFAULT: 'hsl(var(--fg))',
          muted: 'hsl(var(--fg-muted))',
          subtle: 'hsl(var(--fg-subtle))',
          faint: 'hsl(var(--fg-faint))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          deep: 'hsl(var(--accent-deep))',
          soft: 'hsl(var(--accent-soft))',
          hover: 'hsl(var(--accent-hover))',
          ring: 'hsl(var(--accent-ring))',
          // Back-compat aliases (cyan ⇒ Aurora cyan)
          cyan: 'hsl(var(--accent-cyan))',
          'cyan-bright': 'hsl(var(--accent-cyan-bright))',
        },
        violet: {
          DEFAULT: 'hsl(var(--violet))',
        },
        success: 'hsl(var(--success))',
        error: 'hsl(var(--error))',
        warning: 'hsl(var(--warning))',
        status: {
          // Back-compat aliases
          ok: 'hsl(var(--status-ok))',
          warn: 'hsl(var(--status-warn))',
        },

        'border-strong': 'hsl(var(--border-strong) / 0.22)',
        'border-stronger': 'hsl(var(--border-stronger) / 0.32)',

        // shadcn compatibility — CVA recipes look up these names
        background: 'hsl(var(--bg))',
        foreground: 'hsl(var(--fg))',
        border: 'hsl(var(--border) / 0.14)',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--accent-ring))',
        primary: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--bg-deep))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--bg-paper))',
          foreground: 'hsl(var(--fg))',
        },
        muted: {
          DEFAULT: 'hsl(var(--bg-paper))',
          foreground: 'hsl(var(--fg-muted))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--error))',
          foreground: 'hsl(var(--bg-deep))',
        },
        card: {
          DEFAULT: 'hsl(var(--bg-paper))',
          foreground: 'hsl(var(--fg))',
        },
        popover: {
          DEFAULT: 'hsl(var(--bg-paper))',
          foreground: 'hsl(var(--fg))',
        },
      },
      borderRadius: {
        card: '2rem',
        lg: '0.75rem',
        md: '0.5rem',
        sm: '0.375rem',
      },
      fontFamily: {
        // Foundry · Aurora typography
        // - sans: alias of display so legacy `font-sans` still resolves to the display face
        // - display: Inter, the editorial headline family
        // - wordmark: Archivo Black, used only for the striped "ASL PILOT" nav mark
        // - mono: JetBrains Mono, the BODY default (Aurora uses mono for body copy)
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        wordmark: ['"Archivo Black"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"SF Mono"', 'monospace'],
      },
      fontSize: {
        hero: ['clamp(2.5rem, 6vw, 5rem)', { lineHeight: '1.05' }],
      },
      backgroundImage: {
        'grad-primary': 'var(--grad-primary)',
        'grad-glow-a': 'var(--grad-glow-a)',
        'grad-glow-b': 'var(--grad-glow-b)',
        'grad-card': 'var(--grad-card)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        pop: 'var(--shadow-pop)',
      },
    },
  },
  plugins: [animate],
} satisfies Config;
