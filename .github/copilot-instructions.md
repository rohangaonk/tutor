# Copilot Instructions

This project follows a structured roadmap defined in [`ROADMAP.md`](../ROADMAP.md) at the repo root.

### Your Primary Directive

**Before writing any code, always read `ROADMAP.md` first.**

Use it to:
- Understand what phase and step is currently active

---

## 📋 Roadmap Protocol

### Reading the Roadmap

At the start of every session or task:
1. Open and read `ROADMAP.md` in full
2. Identify the **current active step** — the first item that is NOT marked ✅
3. Confirm your understanding with the developer before proceeding:
   > _"Based on the roadmap, the current step is [X]. Should I proceed with this?"_

### Marking Steps as Done

When a step or phase is fully completed:
1. Mark it with ✅ at the start of the line
2. Do not implement steps beyond the current active one unless explicitly asked

## 🚫 Things to Avoid
- Do not add dependencies without asking first
- Do not refactor code outside the scope of the current step
- Do not create new services or databases that aren't in the roadmap
- Do not mark a step as ✅ unless the developer has confirmed it's complete

## ✅ Definition of Done (per step)

A roadmap step is considered complete when:
- The feature/task described is implemented and manually verifiable
- Relevant unit or integration tests exist (if the roadmap step includes testing)
- No debug code, hardcoded values, or `TODO`s are left from this step
- `ROADMAP.md` has been updated with ✅
