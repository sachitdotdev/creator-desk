
---
name: creator-desk-ui-rules
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers: []
---

# Creator Desk UI Rules

You are an expert React and TypeScript developer for the Creator Desk UI.

Rules:

1. **ROUTING**: Always use `useNavigate` from `react-router-dom` for button clicks that change pages. Never use `<a href>` for internal routing.
2. **STATE POLLING**: The video list relies on polling. Do not break the `setInterval` or React Query logic. If a status isn't updating, check the string match (e.g., `status === 'done'`).
3. **API CALLS**: All backend API calls must be placed in `frontend/src/lib/api.ts`. Do not put `fetch()` directly inside components unless absolutely necessary.
4. **STYLING**: Use Tailwind CSS. If a button is not rendering, check if it's missing an `onClick` handler or if it's hidden by `className` flex/display rules.
5. **TARGETED EDITS**: Do not rewrite entire `.tsx` files. Find the specific line with a Python script using `.replace()` and patch it.

