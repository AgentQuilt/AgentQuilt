# AgentQuilt

AgentQuilt is an open-source platform for running AI agents for a small business.

The planned agents will:

- update websites
- answer customers through Telegram, WhatsApp, Viber and web chat
- share business knowledge stored in your own database
- record the actions they take
- support approval and rollback where possible

AgentQuilt is designed to be self-hosted. You control where it runs, what information it stores and what agents are allowed to do.

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
