# Hermes Agent

## What this add-on does

This add-on is a thin Home Assistant wrapper around the official [Hermes Agent](https://github.com/NousResearch/hermes-agent) Docker image. Home Assistant manages the container; Hermes manages its own startup and gateway lifecycle.

The container starts Hermes with `hermes gateway run` and exposes its OpenAI-compatible API on TCP port `8642` for clients such as Open WebUI. Hermes logs remain attached to the container's stdout and stderr, so they appear in the Home Assistant add-on log.

## Storage layout

Home Assistant's persistent add-on data mount is provided at `/opt/data`, Hermes' normal Docker home. Hermes owns its runtime state there, including:

- `/opt/data/config.yaml`
- `/opt/data/.env`
- `/opt/data/SOUL.md`
- `/opt/data/sessions/`
- `/opt/data/memories/`
- `/opt/data/skills/`
- `/opt/data/workspace/`

## Basic setup

1. Configure Hermes directly in `/opt/data/config.yaml` and `/opt/data/.env` using the upstream Hermes documentation. This add-on does not translate Home Assistant options into Hermes configuration.
2. Start the add-on and use its log to confirm that `hermes gateway run` has started.
3. Configure Open WebUI to reach the Home Assistant host on port `8642`.

If you want the full upstream setup flow, install notes, and provider details, see the official Hermes quickstart: https://hermes-agent.nousresearch.com/docs/getting-started/quickstart.

## Notes

- This add-on pins Hermes to `v2026.9.21`.
- Supported Home Assistant architectures are `amd64` and `aarch64`.
- There is no Home Assistant ingress UI, web terminal, model/provider option, or API-key option.
- API authentication and Open WebUI API-key wiring are not configured by this add-on yet.
