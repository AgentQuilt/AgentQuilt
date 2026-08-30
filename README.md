# AgentQuilt

AgentQuilt is an open-source harness for running AI agents in an organisation. The harness carries what every agent needs: users, memory, permissions, approvals and a record of every action. What an agent does for the business lives in skills, plain instructions the harness executes, so an organisation can grow its agents without changing the platform's code.

Its planned agents will:

- update websites
- answer customers through Telegram, WhatsApp, Viber and web chat
- share business knowledge stored in your own database
- record the actions they take
- support approval and rollback where possible

AgentQuilt is designed to be self-hosted. You control where it runs, what information it stores and what agents are allowed to do.

## Who it is for

Small companies first: businesses of three to thirty people that run on consumer messengers and have no systems team. Later, teams inside larger organisations that need governance over agents working across the tools they already use. The harness is free and open; the engagement that installs and operates it is where the cost sits.

## What it is not

- not a model provider and not a chat wrapper
- not hosted software at the start; you run it
- no writing into legacy systems in the first scope: read first, write-back is on the roadmap
- no autonomous payments or bookings
- no per-seat productivity tool; it is the company's own system, running where the company decides

## Roadmap

Development is planned in these stages:

1. Publish the architecture and design records.
2. Create the design system and interface mock-ups.
3. Build the core backend, including memory, approvals, action history and rollback.
4. Add the first agents: personal chat, business chat, knowledge management and Telegram support.
5. Add WhatsApp, Viber and web chat to a shared inbox.
6. Add a website management agent.
7. Package the platform for straightforward self-hosting.
8. Allow users to create and configure their own agents.

Each stage will be released when it is ready.

## Where this stands

As of 30 August 2026, the project is in stage 1.

- The executive spec (what the product is, who it is for, what it is not, the riskiest assumptions) is written and locked.
- The system structure and the design records behind it are settled in the private design notes. Publishing them here is stage 1 and has not happened yet.
- The build order is settled: a walking skeleton first (one governed multi-user chat turn on a web thread, with the record of actions, approvals and permissions in place from the first database migration), then the personal chat and the knowledge base, then Telegram support for a first pilot business, then the admin screens, then the wider channel and self-hosting work in stages 5 to 8.
- No product code exists. The repository holds the development framework described below.

This section is updated when a stage changes.

## Repository contents

The repository currently contains the development framework used to build and review the project:

- `AGENTS.md`: instructions for coding agents
- `REVIEW.md`: review requirements for every change
- `.claude/`: agent definitions, rules, skills and hooks
- `docs/`: project documentation, starting with the provenance rule

Product code will be added in a later development stage.

## Development principles

AgentQuilt is being designed around a few practical requirements:

- business data stays under the operator's control
- agent actions are recorded
- sensitive actions can require approval
- reversible actions include enough information to roll them back
- shared knowledge has a clear source and can be corrected

The repository history records how these decisions and the resulting code change over time.

## Author

AgentQuilt is created and maintained by Emiliyan Tanev.

## Licence and name

The code is licensed under Apache-2.0. See `LICENSE`.

AgentQuilt is a trademark of the author. The name and logo are not covered by the software licence. See `TRADEMARK.md`.

Contributions are accepted under the Developer Certificate of Origin. See `CONTRIBUTING.md` and `docs/provenance.md`.
