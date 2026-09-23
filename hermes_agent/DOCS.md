# Hermes Agent

## What this add-on does

This add-on is a thin Home Assistant wrapper around the official [Hermes Agent](https://github.com/NousResearch/hermes-agent) Docker image. Home Assistant manages the container; Hermes manages its own startup and gateway lifecycle.

The container starts Hermes with `hermes gateway run`, exposes its OpenAI-compatible API on TCP port `8642`, and presents Hermes' s6-supervised dashboard through Home Assistant ingress. Hermes logs remain attached to the container's stdout and stderr, so they appear in the Home Assistant add-on log.

## Storage layout

Home Assistant's persistent add-on data mount is provided at `/opt/data`, Hermes' normal Docker home. Hermes owns its runtime state there, including:

- `/opt/data/config.yaml`
- `/opt/data/.env`
- `/opt/data/SOUL.md`
- `/opt/data/sessions/`
- `/opt/data/memories/`
- `/opt/data/skills/`
- `/opt/data/workspace/`

## Home Assistant options

The Configuration page has only the integration-specific settings below. It does not expose Hermes runtime configuration. Hermes exclusively owns `/opt/data/config.yaml` and all other state under `/opt/data`.

- `hass_token`: a Home Assistant Long-Lived Access Token for Hermes' native Home Assistant integration. It becomes `HASS_TOKEN` only in the container runtime environment.
- `hass_url`: an optional Home Assistant Core base URL. It becomes `HASS_URL` when configured. Leave it blank to retain Hermes' upstream default, `http://homeassistant.local:8123`; use only a base URL, not `/api` or an ingress URL.
- `api_server_key`: the required bearer key for OpenAI-compatible clients. It becomes `API_SERVER_KEY`; startup fails without it.

These credentials are separate. The add-on does not log or persist them in Hermes state. `SUPERVISOR_TOKEN` is injected by Supervisor and is neither an add-on option nor a replacement for `HASS_TOKEN` or `API_SERVER_KEY`.

The values are materialized only during add-on startup. Restart the add-on after changing them if Supervisor has not already restarted it.

## Access

- Home Assistant's Open Web UI opens the normal Home Assistant ingress panel for Hermes, under the Home Assistant origin.
- Open WebUI and other compatible clients use TCP port `8642` with the configured `api_server_key`.
- The dashboard has no separate Hermes authentication because it is private to the container. Home Assistant ingress is the browser authentication boundary.

Home Assistant ingress reaches a small compatibility adapter on container port `9119`. It passes HTTP and WebSocket traffic to the upstream s6-supervised dashboard on `127.0.0.1:9120` and translates Supervisor's `X-Ingress-Path` into Hermes' `X-Forwarded-Prefix`. Neither dashboard port is exposed on the host. This preserves SPA routes and prefixed redirects without nginx.

## Home Assistant CLI

The manifest requests the static Supervisor permissions `hassio_api: true` and `hassio_role: manager`. The official `ha` executable is installed at `/usr/local/bin/ha` and uses Supervisor's injected `SUPERVISOR_TOKEN` with the `supervisor` endpoint.

The add-on never creates, copies, logs, or persists another Supervisor token. `homeassistant_api` remains disabled because the requested commands use the Supervisor endpoint, not the Home Assistant Core API proxy.

`ha supervisor info` must be verified in a real Home Assistant OS environment. A normal Docker container does not provide the Supervisor endpoint or token.

If you want the full upstream setup flow, install notes, and provider details, see the official Hermes quickstart: https://hermes-agent.nousresearch.com/docs/getting-started/quickstart.

## Notes

- This add-on pins Hermes to `v2026.9.21`.
- Supported Home Assistant architectures are `amd64` and `aarch64`.
- There is no web terminal, model/provider configuration, nginx, direct dashboard host exposure, configuration synchronizer, or custom process supervisor.
- The official Home Assistant CLI is copied from the pinned `ghcr.io/home-assistant/<arch>-hassio-cli:2026.09.0` image at build time.
