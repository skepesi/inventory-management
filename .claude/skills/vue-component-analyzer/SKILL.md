---
name: vue-component-analyzer
description: Analyzes Vue 3 component structure and reports evidence-backed optimizations for performance and code reuse, without editing files. Use this skill whenever the user asks to analyze, audit, or review a .vue file or client/src folder, asks why a page or view is slow or re-renders too much, wants to find duplicated logic or markup across components, or asks what to extract into a composable or shared component, even if they don't say "skill" or "optimize". Not for fixing a specific bug, writing new components, or backend performance.
---

# Vue Component Analyzer

Analyze Vue 3 components and report the optimizations most worth making. Reader time is the scarce resource: a short list of real, located problems beats a long list of generic advice.

This skill is read-only. Report findings and suggested fixes, then let the user decide what to change. Offer to apply specific findings at the end, but don't edit anything unless they ask.

## Choose the scope

- **A named file:** analyze it, and read the composables and child components it uses when a finding depends on them. Search the rest of `client/src` as well, because reuse findings depend on what other files do.
- **A folder, or "the components" or "the app":** size up every `.vue` file first, then read the largest and most repeated ones closely. Say which files you read closely and which you only scanned.
- **Nothing named:** default to `client/src`, and say so.
- **Only performance or only reuse requested:** lead with that section. Keep the other to anything serious, or mark it out of scope.

Read `client/CLAUDE.md` first if it exists, because project conventions decide what counts as a problem. For example, this repo calls for the Composition API, unique `v-for` keys, validated dates, loading and error states, and API calls centralized in `api.js`. Report a convention break when it causes a performance or reuse problem.

Before rating impact, check that the component is actually used: look for a route in `client/src/main.js` or an import elsewhere. Code that never runs has no user-facing performance cost, so report that as the first finding, and ask whether to delete or connect it instead of rating its internals as if they were live.

## What to look for

### Performance

- **Repeated work in the template:** a method that filters, sorts, or maps, called from the template. It runs on every render, and again for each call. A `computed` caches the result until its dependencies change.
- **Expensive computeds:** nested loops over the same data, or lookups with `.find()` or `.filter()` inside a loop that could use a `Map` or `Set` built once.
- **Unstable `v-for` keys:** an index or non-unique key on a list that can reorder or be filtered. Vue may then reuse the wrong DOM elements and keep stale state, so this can be a correctness bug as well as a performance one.
- **Wasteful fetching:** the same endpoint fetched by several components, requests that run sequentially but could use `Promise.all`, watchers that refetch when client-side filtering would do, or filter changes that fire a request per keystroke with no debounce.
- **Stale responses:** a watcher that reloads data with no guard against an older response arriving after a newer one. This shows wrong data rather than just being slow. Rate it high for typed input or sliders, which fire many requests quickly, and medium for dropdowns.
- **Leaks:** `addEventListener`, `setInterval`, `setTimeout`, or chart instances created without cleanup in `onUnmounted` or `onBeforeUnmount`.
- **Heavy code loaded up front:** views or large modals imported statically when a route-level or `defineAsyncComponent` import would defer them.
- **`v-if` against `v-show`:** `v-if` on something toggled often and costly to rebuild. Only mention this when the toggling is really frequent.
- **Too much reactivity:** large read-only data held deeply reactive when `shallowRef` would do. Only mention this for large data sets.

### Code reuse

- **Duplicated logic:** the same formatter, status-to-class mapping, or fetch and error handling in two or more files. Check `src/composables/` and `src/utils/` first, because the best finding is often that a helper already exists and isn't being used.
- **Duplicated markup:** repeated modal shells, tables, stat cards, or badges that could share a component with slots.
- **Duplicated styles:** the same scoped CSS repeated across components, or hard-coded colors where CSS variables or global classes exist.
- **Oversized components:** as a rough guide from `client/CLAUDE.md`, more than 100 template lines or 150 logic lines. Size alone isn't a finding, so name the separate responsibilities and where you would split them.

## How to judge findings

- **Cite evidence.** Every finding needs `file:line` and what the code does there. If you can't point to it, leave it out.
- **Count before claiming duplication.** Use search to get the real number of files, and read at least two occurrences to confirm they actually do the same thing. Similar names can hide different behavior, and those differences would break a naive extraction. A throwaway script that only reads files is fine for comparing CSS blocks, as long as it writes nothing to the repo.
- **Rate the impact honestly.** Static analysis can't measure speed, so describe the likely effect and don't invent numbers like "40% faster". Consider how large the data really is, using `server/data/*.json` in this repo: filtering 20 rows on each render is cheap, so say so rather than inflating it.
- **Flag changes users would see.** If a suggested extraction would change what appears on screen, such as copies that disagree on currency or labels, say so and leave the choice to the user.
- **Prefer a few useful findings.** Skip anything trivial, and if a component is in good shape, say that. An empty section is a valid result.
- **Note what you can't tell.** Runtime behavior, real data sizes, and browser effects need profiling. Suggest Vue DevTools or the browser Performance panel when a finding depends on them.
- **Don't drift into unrelated review.** Mention an unrelated bug or security issue briefly if you notice one, but keep the report on performance and reuse.

## Report format

Use this structure, ordering findings by value within each section. Put whichever section best answers the request first:

```markdown
# Vue Component Analysis: [scope]

**Summary:** [One or two sentences: overall state and the single best thing to do first.]
**Reviewed:** [Files read closely, and any only scanned.]

## Performance
### 1. [Short problem statement] — Impact: High | Medium | Low · Effort: Small | Medium | Large
- **Where:** `path/File.vue:123`
- **Problem:** [What the code does, and why it matters here.]
- **Suggestion:** [The specific change, with a short before and after if it helps.]

## Code reuse
### 2. [Short problem statement] — Impact: ... · Effort: ...
- **Where:** `path/A.vue:10`, `path/B.vue:42` (N files in total)
- **Problem:** [What is duplicated, and any differences between the copies.]
- **Suggestion:** [What to extract, its proposed name, and where it goes.]

## Suggested order
[A short list: what to do first and why.]

## Decisions for you
[Dead code to delete or connect, and any suggestion that changes what users see. Omit if there are none.]

## Not checked
[Anything needing runtime profiling or left out of scope.]

## Also noticed
[Brief notes on unrelated bugs. Omit if there are none.]

[Closing line: offer to apply findings by number.]
```

Rate **Impact** by what a user or maintainer would notice, and **Effort** by the size of the change. Number findings across both sections so the user can say "apply 1 and 3". If a section has no findings, write "No significant issues found."
