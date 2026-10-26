---
name: Sentinel Oversight
colors:
  surface: '#08132a'
  surface-dim: '#08132a'
  surface-bright: '#2f3952'
  surface-container-lowest: '#030d25'
  surface-container-low: '#101b33'
  surface-container: '#151f37'
  surface-container-high: '#1f2942'
  surface-container-highest: '#2a344d'
  on-surface: '#d9e2ff'
  on-surface-variant: '#c5c6cd'
  inverse-surface: '#d9e2ff'
  inverse-on-surface: '#263049'
  outline: '#8f9097'
  outline-variant: '#44474d'
  surface-tint: '#b9c7e4'
  primary: '#b9c7e4'
  on-primary: '#233148'
  primary-container: '#0a192f'
  on-primary-container: '#74829d'
  inverse-primary: '#515f78'
  secondary: '#b6c6ed'
  on-secondary: '#20304f'
  secondary-container: '#374767'
  on-secondary-container: '#a5b5db'
  tertiary: '#38debb'
  on-tertiary: '#00382d'
  tertiary-container: '#001e17'
  on-tertiary-container: '#00937a'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d6e3ff'
  primary-fixed-dim: '#b9c7e4'
  on-primary-fixed: '#0d1c32'
  on-primary-fixed-variant: '#39475f'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#b6c6ed'
  on-secondary-fixed: '#091b39'
  on-secondary-fixed-variant: '#374767'
  tertiary-fixed: '#5ffbd6'
  tertiary-fixed-dim: '#38debb'
  on-tertiary-fixed: '#002019'
  on-tertiary-fixed-variant: '#005142'
  background: '#08132a'
  on-background: '#d9e2ff'
  surface-variant: '#2a344d'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 16px
  margin: 24px
  container-max: 1440px
---

## Brand & Style

The design system is engineered for high-stakes, data-intensive environments where clarity and rapid cognition are paramount. It adopts a **Corporate / Modern** aesthetic with a lean toward **Minimalism** to reduce cognitive load during critical decision-making.

The brand personality is authoritative, reliable, and precise. It avoids decorative flourishes in favor of functional density. The interface should feel like a high-performance instrument—cold, efficient, and unwavering. Visual hierarchy is established through strict alignment and high-contrast status signaling rather than depth or texture.

## Colors

The palette is optimized for low-light command center environments. The primary background uses a deep navy to reduce eye strain, while surfaces utilize slightly lighter navy shades to create structural separation. 

- **Primary Background:** Used for the main application shell.
- **Surface/Container:** Used for cards and secondary panels to create subtle contrast.
- **Primary Action:** A high-visibility cyan-tinted accent for interactive elements.
- **Functional Colors:** Success Green and Danger Red are reserved strictly for status indicators (Pass/Fail, Clear/Alert) to ensure they retain their psychological urgency.
- **Text:** Crisp white for primary headers, with muted blue-grey for secondary metadata.

## Typography

This design system utilizes **Inter** for all standard UI elements due to its exceptional legibility in data-heavy contexts. A secondary monospace font, **JetBrains Mono**, is introduced specifically for alphanumeric data—such as passport numbers, license plates, and timestamps—to prevent character confusion (e.g., 0 vs O, 1 vs I).

- Use `display-lg` for primary dashboard metrics.
- Use `label-caps` for table headers and small metadata categories.
- Ensure all data tables utilize `data-mono` for tabular numerals, allowing for easier scanning and comparison of vertical columns.

## Layout & Spacing

The layout follows a **Fixed Grid** philosophy on desktop to ensure that critical data points do not shift unexpectedly on large monitors. A 12-column system is used with rigid 16px gutters.

- **Grid:** 12-column layout for desktop; 4-column for mobile.
- **Rhythm:** All margins and paddings must be multiples of 4px.
- **Density:** The system defaults to a "Compact" density model. Content should be grouped logically into modules, with 24px spacing between major functional blocks.
- **Mobile Adaption:** On mobile, sidebars collapse into a bottom navigation or "hamburger" menu, and tables transition into stacked card views to maintain readability of ID credentials.

## Elevation & Depth

To maintain a "Professional/Law Enforcement" aesthetic, this design system avoids heavy shadows. Depth is communicated primarily through **Tonal Layers** and **Low-contrast outlines**.

- **Level 0 (Base):** Primary Navy background.
- **Level 1 (Surfaces):** Cards and panels use a slightly lighter navy hex with a 1px solid border (Opacity 10% white).
- **Level 2 (Interactions):** Active states or modals use a very subtle, tight ambient shadow (Blur 4px, Opacity 20% black) to lift them slightly from the interface.
- **Overlays:** Modals use a 60% opacity dark navy backdrop blur to keep the background context visible while focusing the operator's attention.

## Shapes

The shape language is "Soft" (4px radius) to provide a modern feel without appearing overly casual or consumer-focused. 

- **Components:** Buttons, inputs, and cards use the standard 4px radius.
- **Status Badges:** Use a "Pill" shape (full rounding) to differentiate them from interactive buttons and structural containers.
- **Icons:** Should be stroke-based (2px weight) with squared terminals to match the professional tone of the system.

## Components

### Buttons
Primary buttons use the Tertiary accent color with black/dark-navy text for maximum contrast. Secondary buttons use a ghost style with 1px borders.

### Cards
Cards are the primary structural unit. Every card must have a `Card Header` with a 1px bottom border. Headers should include an icon (left-aligned) and a title in `label-caps`.

### Status Badges
High-contrast badges are used for "Pass," "Flag," or "Inquiry" states. These should use a solid background of the status color with high-contrast text.

### Input Fields
Fields must have explicit labels and placeholder text that illustrates the expected format (e.g., "YYYY-MM-DD"). On focus, the border color shifts to the primary accent color.

### Data Tables
Tables are the heart of the system. Use zebra-striping (subtle opacity difference) for long rows. Action buttons in tables (e.g., "View Profile") should be icon-only to save horizontal space.

### Additional Components
- **Scanner Feed Window:** A dedicated container for live video or document scans, featuring a "Scanning" animation overlay and a "Capture" action.
- **Search Command Bar:** A global, prominent search bar at the top of the interface for rapid querying of names or document numbers.