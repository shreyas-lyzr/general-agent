# general-agent

A general-purpose [GAP](https://github.com/gitagent-protocol) (gitagent protocol) agent.

Driven via [gitagent](https://github.com/gitagent/gitagent) / gitclaw and intended to be invoked from `@computeragent` infrastructure — e.g. through a Slack bot or the `/run`, `/tasks`, or `/sandboxes` endpoints of a ComputerAgent harness server.

## Files

- `agent.yaml` — GAP manifest (model, runtime, version)
- `SOUL.md` — system prompt / persona

## Usage

```bash
# As a one-shot task via the ComputerAgent SDK
runTask({
  source: { kind: "github", repo: "shreyas-lyzr/general-agent" },
  harness: "gitagent",
  envs: { ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY },
  message: "Investigate the current directory and summarize what you find.",
});
```
