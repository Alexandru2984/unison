# Idea Evolution frontend

React 19, TypeScript, Vite and React Flow. See the [project README](../README.md) for setup, product behavior and verification.

- `npm run dev`: local workspace with `/api` and `/ws` proxying to loopback port 8080.
- `npm run build`: type check and production bundle, with the graph loaded separately.
- `npm run lint -- --max-warnings=0`: lint source and browser tests.
- `npm test`: bounded comparison, export and reconciliation checks.
- `npm run test:e2e`: Chromium product/accessibility checks against the built frontend and isolated fixtures.

Drafts/bookmarks/theme use local storage. Public text is rendered through React text nodes. API errors and failed live connections remain visible to the user.
