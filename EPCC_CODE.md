# Implementation: Inventory CSV Export

**Mode**: default | **Date**: 2026-11-05 | **Status**: Build passes, not tested in a browser

## 1. Changes (3 files)
**Modified**: `client/src/views/Inventory.vue` - Export button, `csvText()` and `exportCsv()` helpers, scoped styles
**Modified**: `client/src/locales/en.js`, `client/src/locales/ja.js` - `inventory.exportCsv` label

## 2. Quality (Build passes | Browser not run | Tests none)
**Build**: `npm run build` passes.
**Browser**: Playwright permission not granted, so the button and the downloaded file are untested.
**Tests**: None added. The client has no test runner, and this feature has no backend change.

## 3. Decisions
**Client-side export**: Built from `filteredItems` | Why: the file matches what the user sees, with filters, search and sort applied | Alt: new backend endpoint
**Numeric columns**: Plain numbers with no currency symbol | Why: spreadsheets can sum them, but the file does not state a currency
**Formula neutralisation**: Quote prefix on text fields only | Why: stops spreadsheets running cell text as formulas without altering numbers

## 4. Handoff
**Blockers**: Test the button in the browser, and open a downloaded file in Excel.
**TODOs**: None. The prettier reformatting in `Inventory.vue` was kept, so the diff includes unrelated template and script changes.
**PR**: #5
