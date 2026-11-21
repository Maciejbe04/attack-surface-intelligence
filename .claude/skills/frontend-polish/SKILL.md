---
name: frontend-polish
description: Polishes existing SurfaceX UI for spacing, alignment, states, motion, and responsiveness without redesigning from scratch. Use when refining components, fixing visual inconsistencies, improving empty/loading/error states, or when the user asks to polish, tidy, or clean up the frontend.
---

# Frontend Polish

Polish improves an existing design. Do not rebrand or reinvent IA unless asked.

## Pass order

1. **Alignment** — consistent columns, baseline grids, toolbar heights, table cell padding.
2. **Spacing** — use spacing tokens; remove one-off margins; tighten noisy gaps.
3. **Typography** — truncate long hosts with tooltip/title; tabular nums for ports/dates/ETA.
4. **States** — loading skeletons/spinners, empty copy that says what to do next, inline errors.
5. **Feedback** — button pending, disabled reason, toast/inline success for import/export.
6. **Motion** — 2–3 intentional motions max (e.g. progress bar, row highlight on `CHANGED`).
7. **Responsive** — toolbars wrap cleanly; tables scroll horizontally before squashing meaning.
8. **Focus** — visible focus rings; keyboard order matches visual order.

## SurfaceX specifics

- Preserve lifecycle colors and labels; do not restyle status ad hoc per page.
- Confidence and evidence should stay scannable: score + short proof, not walls of JSON.
- Scan ETA must remain readable during polish (no decorative obscuring).
- Forms (targets, import): validate inline; keep primary submit stable in position.
- Never polish away RBAC affordances (missing destroy action for `viewer` is correct).

## Do / don't

| Do | Don't |
|---|---|
| Reuse tokens | Invent new hex per component |
| Fix uneven padding | Add more cards/shadows |
| Improve empty states | Add emoji illustrations |
| Subtle row hover | Glow / gradient hover |
| Clip with meaning | Hide critical status |

## Done when

- Visual noise decreased without losing data density.
- Same component looks identical across pages.
- Keyboard and narrow-width checks pass.
- Diff is mostly CSS/class/layout, not product rewrites.
