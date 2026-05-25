---
description: Frontend guidelines for Next.js, shadcn, TanStack Query, Zustand
applyTo: 'apps/web/src/app/**,apps/web/src/components/**,apps/web/src/hooks/**,apps/web/src/stores/**'
---

# Copilot Instructions — Frontend

This file governs all frontend work in this project.

---

## 🧱 Stack

| Concern | Library |
|---|---|
| Framework | Next.js 14+ (App Router) |
| UI Components | shadcn/ui |
| Styling | Tailwind CSS |
| Server State / Data Fetching | TanStack Query (`@tanstack/react-query`) |
| Client / Global State | Zustand |
| Forms | React Hook Form + Zod |
| AI Streaming | Vercel AI SDK (`ai` package) |

Do not introduce alternatives to any of the above without asking first.

---

## 📁 Folder Structure

Follow this structure strictly. Do not invent new top-level folders.

```
apps/web/src/
├── app/                        # Next.js App Router pages and layouts
│   ├── (auth)/                 # Route group: login, signup
│   │   └── login/
│   │       └── page.tsx
│   ├── (dashboard)/            # Route group: authenticated app shell
│   │   ├── layout.tsx          # Shared dashboard layout (NavBar + AuthGuard)
│   │   ├── page.tsx            # Home / landing page
│   │   └── [feature]/
│   │       ├── page.tsx
│   │       └── loading.tsx
│   └── api/                    # Route handlers (API endpoints)
│       └── [resource]/
│           └── route.ts
│
├── components/
│   ├── ui/                     # shadcn-generated components (do not edit manually)
│   ├── layout/                 # Shared layout components (NavBar, AuthGuard)
│   └── [feature]/              # Feature-specific components, co-located
│
├── hooks/                      # Custom React hooks (useXxx.ts)
├── lib/                        # Shared utilities, API clients, constants
│   ├── api.ts                  # Axios / fetch wrapper
│   ├── queryClient.ts          # TanStack Query client config
│   └── validators/             # Zod schemas
│
├── stores/                     # Zustand stores (useXxxStore.ts)
└── types/                      # Shared TypeScript types and interfaces
```

---

## 🎨 UI & Component Rules

### Use shadcn/ui first
- Always reach for a shadcn component before writing custom UI.
- Install components via CLI: `npx shadcn@latest add <component>`
- Never edit files inside `components/ui/` directly. Extend via wrapper components.

### Wrapper pattern for shadcn components
When you need to customise a shadcn component, wrap it — do not modify the source:
```tsx
// components/tutor/TutorCard.tsx
import { Card, CardContent, CardHeader } from "@/components/ui/card"

export function TutorCard({ title, children }: TutorCardProps) {
  return (
    <Card className="rounded-xl border border-border/50 shadow-sm">
      <CardHeader className="pb-2">{title}</CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}
```

### Tailwind conventions
- Use Tailwind utility classes exclusively. No inline `style={{}}` unless strictly necessary (e.g. dynamic values not achievable otherwise).
- Use `cn()` from `@/lib/utils` to merge conditional classes.
- Follow a **clean SaaS aesthetic**: neutral backgrounds, strong typographic hierarchy, consistent spacing scale (`gap-4`, `gap-6`, `gap-8`).
- Dark mode is supported via `dark:` variants from day one.

---

## 🔄 Data Fetching with TanStack Query

### All server data goes through TanStack Query
```tsx
// hooks/useLessons.ts
export function useLessons(topicId: string) {
  return useQuery({
    queryKey: ["lessons", topicId],
    queryFn: () => api.get(`/topics/${topicId}/lessons`),
    staleTime: 1000 * 60 * 5, // 5 min
  })
}
```

### Rules
- Query keys must be **arrays** and **descriptive**: `["lessons", topicId]`, not `["data"]`.
- Set explicit `staleTime` — do not rely on default (0) for AI responses.
- Mutations use `useMutation` and call `queryClient.invalidateQueries` on success.
- Never fetch inside `useEffect` — always use a query hook.

### AI streaming responses
Use the Vercel AI SDK `useChat` / `useCompletion` hooks for streaming:
```tsx
import { useChat } from "ai/react"

const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
  api: "/api/chat",
})
```
Do not manually manage streaming state with `useState` + `fetch`.

---

## 🗂 Global State with Zustand

Only put **client-only, cross-component state** in Zustand. Server data stays in TanStack Query.

```ts
// stores/useSessionStore.ts
import { create } from "zustand"

interface SessionState {
  activeTopic: string | null
  setActiveTopic: (id: string) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  activeTopic: null,
  setActiveTopic: (id) => set({ activeTopic: id }),
}))
```

**Good candidates for Zustand:** sidebar open/closed, active lesson/topic, user preferences, onboarding step.  
**Bad candidates:** data from the API, auth state (use a server session / Next.js middleware instead).

---


## ⚙️ Server vs Client Components

| Use `"use client"` when | Stay as Server Component when |
|---|---|
| Using hooks (`useState`, `useEffect`, TanStack Query, Zustand) | Fetching data with `async/await` directly |
| Handling events (`onClick`, `onChange`) | Rendering static or SEO content |
| Using browser APIs | Accessing `cookies()`, `headers()` |

### Rules
- Default to **Server Components**. Add `"use client"` only when needed.
- Push `"use client"` as far down the tree as possible — keep layouts and pages as server components.
- Never use `"use client"` at the page level unless the entire page is interactive.

---

## 🚫 Things to Avoid

- Do not use `fetch` inside `useEffect` for server data — use TanStack Query.
- Do not add a new UI library (MUI, Chakra, Mantine, etc.) — we use shadcn only.
- Do not write CSS files or CSS modules — Tailwind only.
- Do not put business logic inside components — extract to hooks or `lib/`.
- Do not use `any` in TypeScript — type everything explicitly.
- Do not add a Zustand store for data that belongs in TanStack Query.
- Do not create new components without checking if shadcn already has one.

---