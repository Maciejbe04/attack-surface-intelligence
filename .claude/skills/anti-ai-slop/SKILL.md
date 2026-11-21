---
name: anti-ai-slop
description: Blocks generic AI UI aesthetics and enforces distinctive, restrained SurfaceX visuals. Use when creating or editing React/CSS UI, dashboards, landing pages, components, themes, or when the user mentions AI slop, generic design, or visual cleanup.
---

# Anti AI Slop

SurfaceX is an attack-surface operations tool. Prefer sharp, credible, data-first UI. Reject templates that look like every other AI demo.

## Hard bans

Do not ship these defaults:

1. Purple-on-white or purple-to-indigo gradient themes.
2. Warm cream background (~`#F4F1EA`) with high-contrast serif display and terracotta accent.
3. Broadsheet layout: hairline rules, zero radius, dense newspaper columns.
4. Default dark mode with neon/glow accents.
5. `rounded-full` pill clusters for navigation, filters, or tags.
6. Multi-layer soft shadows and glassmorphism stacks.
7. Emoji as decoration, section icons, or empty-state filler.
8. Default font stacks: Inter, Roboto, Arial, system-ui as the primary brand face.
9. Hero with floating badges, stickers, promo chips, or stat strips.
10. Card grids when a plain list/table communicates better.

## Prefer instead

- One clear visual direction with CSS variables (`--color-*`, `--font-*`, `--space-*`).
- Expressive but readable typography: one display face + one text face, both purposeful.
- Atmosphere from subtle structure (borders, spacing, muted surfaces), not gradients-as-identity.
- Status color only for lifecycle meaning: `NEW`, `CHANGED`, `MISSING`, `FLAKY`, `GONE`.
- Dense operational layouts: tables, filters, timelines — not marketing card mosaics.
- Motion only when it clarifies hierarchy or progress (scan ETA, state change).

## Quick rejection test

If removing the logo would make the screen indistinguishable from a generic SaaS/AI template, redesign.

## Workflow

1. Before styling, state the visual direction in one sentence.
2. Define tokens first; avoid one-off hex values in components.
3. Build the primary view (dashboard or target list) before decorative chrome.
4. Remove any banned pattern that slipped in.
5. Re-check on mobile width and with long hostnames/CIDRs.
