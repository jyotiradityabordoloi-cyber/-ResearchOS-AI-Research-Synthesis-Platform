# ResearchOS frontend

Next.js 16 (App Router) · Tailwind CSS 4 · shadcn/ui · TanStack Query · Recharts.

```bash
npm install
npm run dev -- -p 3010     # expects the API at NEXT_PUBLIC_API_URL (default http://localhost:8010)
npx tsc --noEmit && npm run lint && npm run build
```

All data comes from the FastAPI backend; see the [project README](../README.md) for setup, Docker,
AI providers and tests.
