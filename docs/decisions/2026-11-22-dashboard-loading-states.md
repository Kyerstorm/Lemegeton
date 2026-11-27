# Dashboard Loading and Request-State Decision

**Date:** 2026-11-22  
**Status:** Accepted; implementation in progress

## Context

The dashboard used a page-wide spinner while bootstrapping, displayed placeholder values before initial data arrived, and reused a broad refresh flag for requests owned by different pages. Audit and system data were fetched once in the initial guild refresh and then fetched again when their pages opened. Some failures were rendered as empty data or inserted into the runtime log output.

These are symptoms of unclear request ownership and conflated UI states, not a shortage of loading indicators.

## Decision

Use one shared `Skeleton` primitive and compose skeletons to match the actual shell or section layout. Keep the initial dashboard skeleton separate from feature-specific skeletons.

Each independently loaded section owns its `loading` and `error` state. A section's lifecycle follows:

- **Initial load:** show a layout-matched skeleton only where data has not yet been confirmed.
- **Background refresh:** keep the last confirmed content visible; do not replace it with a skeleton.
- **Success with no records:** show the section's genuine empty state.
- **Failure:** retain any last confirmed content, show a local actionable error, and offer retry for that request.
- **Small local mutation:** use compact pending feedback on the affected control; do not replace a page with a skeleton.

The same shell skeleton is used by the root Next.js loading boundary and the client bootstrap state. Skeleton motion stops when `prefers-reduced-motion` is active.

HTTP authorization, rate-limit and service-unavailable outcomes are mapped to safe user-facing messages. The browser remains a presentation layer: Rust continues to enforce session, consent, CSRF, guild and permission checks.

## Consequences

- A slow or failed section does not hide unrelated dashboard content.
- Successful empty responses remain distinct from requests that have not completed.
- Periodic refreshes no longer flash loading placeholders over confirmed content.
- A request is not duplicated merely because its page became active after the initial guild refresh.
- The bootstrap failure screen is distinct from policy consent; consent retry is reserved for the consent endpoint.

## Scope

This decision does not change API routes, authorization rules, persistence, bot behavior, or the shared Discord emoji palette. It does not make the dashboard release-complete. Other planned page and feature modules remain subject to independent inspection and implementation.

## Re-audit

Test first load, slow responses, empty success, request failure, retry, background refresh, guild switching, rate limiting, service unavailability, expired sessions, and reduced-motion behavior. Revisit section ownership if new data requests are added.
