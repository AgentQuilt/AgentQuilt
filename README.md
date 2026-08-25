# AgentQuilt

Every time you send a message, the model is a stranger. It has no memory of its own, and nothing it did yesterday is on record today. AgentQuilt is an open-source platform that fixes both for a company running agents on its own systems. Several people share one memory, curated by the company itself, in its own database. Every action an agent takes leaves a receipt, and every receipt says how to walk it back. Your knowledge stays with you, not with a vendor.

It is not a chatbot builder. It is not a hosted service. You run it.

The bet underneath: thick skills, thin code. The instructions your company writes carry its processes. The code stays small and stays put.

## Where This Is Going

The build runs in the order people can see it.

1. The architecture on paper. Twenty-seven design records and one structure document, published as the first spec release.
2. Design before code. A design system made of reusable parts, then a mock-up of every screen, so anyone can open this repository and see what the finished thing is for.
3. The backend behind the mock-ups. Memory, receipts and approvals, wired to those screens, in your own database.
4. The first agents on it. A personal chat thread, messaging for a company chatbot, a knowledge hub, and client-facing support agents on Telegram.
5. Self-hosting in an evening. One image, one compose file.

Each step ships when it is finished and gets a dated entry in the changelog. No step is skipped to look further ahead.

## What Is in This Repository

The working setup for the coding agents that build AgentQuilt. It is published with the product so the method can be reviewed too.

- `AGENTS.md`: the guide every agent reads first. What the product is, the working agreement, the review contract, the model routing.
- `REVIEW.md`: the contract every change is judged against.
- `.claude/`: the agents, rules, skills and hooks that do the building.

Product code arrives with step 3.

## Who Is Building This

I am Emiliyan. I trained as a management accountant and spent my working life as an SAP planning architect for finance teams. That work teaches one thing early: before a company trusts a system with a decision, it wants a record, an owner, and a way back. AgentQuilt is that lesson, built in public, one finished step at a time. I am moving into applied AI engineering with it. The commits are the evidence.

## Origins

AgentQuilt's design draws on lessons from an internal agent platform the author built in prior professional work. No code, prompt, schema, data or configuration from that work is reused, and it is not named. The full rule is in `docs/provenance.md`.

## Licence and Name

Apache-2.0, see `LICENSE`. AgentQuilt™ is a trademark of the author; the name and any logo are not covered by the licence, see `TRADEMARK.md`. Contributions are accepted under the Developer Certificate of Origin, see `CONTRIBUTING.md`.

Many patches, each its own, stitched into one thing you can use.
