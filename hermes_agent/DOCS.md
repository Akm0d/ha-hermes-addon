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

The Configuration page intentionally has one option:

- `config_yaml`: the native Hermes `config.yaml` editor.

`/opt/data/config.yaml` is authoritative. Upstream Hermes initializes it first; the add-on then validates its mapping root and mirrors its exact contents to `config_yaml`. Startup never overwrites the native file from Home Assistant options.

While running, a small inherited-s6 service compares content hashes. A changed native file is mirrored to Home Assistant without a restart. A changed, valid Home Assistant option is atomically written to the native file, then requests one Supervisor-managed app restart and exits. The restart request is never made for native-to-option mirroring, preventing feedback loops.

The initial native-to-option mirror replaces persisted options with only `config_yaml`, removing obsolete legacy keys without translating them.

Example raw `config_yaml`:

```yaml
model:
  provider: custom
  default: my-model
  base_url: http://example/v1

dashboard:
  basic_auth:
    username: admin
    password: CHANGE_ME
    secret: CHANGE_ME_TO_A_LONG_RANDOM_SECRET
```

Use Hermes' native dashboard authentication configuration. When the dashboard binds to `0.0.0.0`, Hermes enforces its own authentication policy; invalid configuration is reported in the add-on log.

## Access

- Home Assistant's Open Web UI opens the normal Home Assistant ingress panel for Hermes, under the Home Assistant origin.
- Open WebUI and other compatible clients should use TCP port `8642` for the OpenAI-compatible API.
- The add-on does not create an API secret; Hermes' native authentication behavior remains in effect.

Home Assistant ingress reaches a small compatibility adapter on container port `9119`. It passes HTTP and WebSocket traffic to the upstream s6-supervised dashboard on private port `9120` and translates Supervisor's `X-Ingress-Path` into Hermes' `X-Forwarded-Prefix`. Port `9119` is not exposed on the host. This preserves SPA routes and prefixed redirects without nginx.

## Home Assistant CLI

The manifest requests the static Supervisor permissions `hassio_api: true` and `hassio_role: manager`. The official `ha` executable is always available to Hermes and uses the injected `SUPERVISOR_TOKEN` with the `supervisor` endpoint.

The add-on maps that token into the CLI's runtime token variable only; it never creates, copies, logs, or persists another Supervisor token. `homeassistant_api` remains disabled because the requested commands use the Supervisor endpoint, not the Home Assistant Core API proxy.

`ha supervisor info` must be verified in a real Home Assistant OS environment. A normal Docker container does not provide the Supervisor endpoint or token.

If you want the full upstream setup flow, install notes, and provider details, see the official Hermes quickstart: https://hermes-agent.nousresearch.com/docs/getting-started/quickstart.

## Notes

- This add-on pins Hermes to `v2026.9.21`.
- Supported Home Assistant architectures are `amd64` and `aarch64`.
- There is no web terminal, model/provider option, API-key option, nginx, or direct host exposure for the dashboard.
- The official Home Assistant CLI is copied from the pinned `ghcr.io/home-assistant/<arch>-hassio-cli:2026.09.0` image at build time.
