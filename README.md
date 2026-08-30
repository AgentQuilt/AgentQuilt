# AgentQuilt

AgentQuilt is an open-source, self-hosted harness for running AI agents inside an organisation. It handles the parts every agent needs: users, memory, permissions, approvals and an audit trail of what happened.

Business-specific behaviour lives in skills. These are plain instructions that agents can run, which means an organisation can add or change what its agents do without rewriting the platform itself.

The project aims to support agents that can:

* update websites
* answer customers through Telegram, WhatsApp, Viber and web chat
* share business knowledge stored in the organisation's own database
* keep a record of the actions they take
* ask for approval and roll back actions where possible

You choose where AgentQuilt runs, what data it stores and what each agent is allowed to do.

## Who it is for

AgentQuilt is being built first for small companies with three to thirty people. These businesses often rely on consumer messaging apps and do not have a dedicated systems team.

It may later suit teams inside larger organisations that need to control how agents work across their existing tools.

The software is free and open source. Costs come from the work needed to install, configure and operate it for a particular business.

## Roadmap

Development is planned in eight stages:

1. Publish the architecture and design records.
2. Create the design system and interface mock-ups.
3. Build the core backend, including memory, permissions, approvals, action history and rollback.
4. Add the first agents for personal chat, business chat, knowledge management and Telegram support.
5. Bring WhatsApp, Viber and web chat into a shared inbox.
6. Add an agent for managing websites.
7. Package the platform for self-hosting.
8. Let users create and configure their own agents.

Stages will be released when they are ready.

## Development principles

AgentQuilt is being designed around a few firm requirements:

* Business data stays under the operator's control.
* Agent actions are recorded.
* Sensitive actions can require approval.
* Reversible actions store enough information to undo them.
* Shared knowledge has a clear source and can be corrected.

The repository history will show how these decisions and the resulting code change over time.

## Author

AgentQuilt is created and maintained by Emiliyan Tanev.

## Licence and name

The code is licensed under Apache-2.0. See `LICENSE`.

AgentQuilt is a trademark of the author. The software licence does not cover the name or logo. See `TRADEMARK.md`.

Contributions are accepted under the Developer Certificate of Origin. See `CONTRIBUTING.md` and `docs/provenance.md`.

