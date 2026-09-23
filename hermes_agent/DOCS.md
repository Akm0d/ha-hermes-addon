# Hermes Agent

## What this add-on does

This add-on is a thin Home Assistant wrapper around the official [Hermes Agent](https://github.com/NousResearch/hermes-agent) Docker image. Home Assistant manages the container; Hermes manages its own startup and gateway lifecycle.

The container starts Hermes with `hermes gateway run`, exposes its OpenAI-compatible API on TCP port `8642`, and uses Hermes' own s6-supervised dashboard on TCP port `9119`. Hermes logs remain attached to the container's stdout and stderr, so they appear in the Home Assistant add-on log.

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

- `config_yaml`: the complete native Hermes YAML configuration.

At every app start, the add-on validates that `config_yaml` is YAML whose document root is a mapping, then atomically writes it to `/opt/data/config.yaml` before Hermes' own initialization runs. The raw YAML text is preserved rather than translated into Home Assistant fields.

Home Assistant options are authoritative at startup. Hermes may change `config.yaml` while running, but the next app restart replaces it with `config_yaml`; there is no bidirectional synchronization or long-running configuration watcher.

On upgrade, a one-time startup migration removes obsolete Home Assistant options through the Supervisor options API. If native YAML is still empty, it preserves only the previously verified model provider, default-model, and base-URL values by writing their native Hermes `model` mapping into `config_yaml`. All other obsolete fields, including old provider credentials, are discarded rather than translated. Once the Supervisor accepts that update, its persisted option set contains only `config_yaml`.

This app does not implement an internal restart watcher. Current Supervisor behavior after saving options must be confirmed on the target HAOS release: if it restarts the app, the new document is materialized during that startup; otherwise the user must restart the app from Home Assistant. A live HAOS validation is required before claiming automatic apply-on-save.

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

- Home Assistant's Open Web UI button opens the Hermes dashboard on TCP port `9119`.
- Open WebUI and other compatible clients should use TCP port `8642` for the OpenAI-compatible API.
- The add-on does not create an API secret; Hermes' native authentication behavior remains in effect.

## Home Assistant CLI

The manifest requests the static Supervisor permissions `hassio_api: true` and `hassio_role: manager`. The official `ha` executable is always available to Hermes and uses the injected `SUPERVISOR_TOKEN` with the `supervisor` endpoint.

The add-on maps that token into the CLI's runtime token variable only; it never creates, copies, logs, or persists another Supervisor token. `homeassistant_api` remains disabled because the requested commands use the Supervisor endpoint, not the Home Assistant Core API proxy.

`ha supervisor info` must be verified in a real Home Assistant OS environment. A normal Docker container does not provide the Supervisor endpoint or token.

If you want the full upstream setup flow, install notes, and provider details, see the official Hermes quickstart: https://hermes-agent.nousresearch.com/docs/getting-started/quickstart.

## Notes

- This add-on pins Hermes to `v2026.9.21`.
- Supported Home Assistant architectures are `amd64` and `aarch64`.
- There is no Home Assistant ingress UI, web terminal, model/provider option, or API-key option.
- The official Home Assistant CLI is copied from the pinned `ghcr.io/home-assistant/<arch>-hassio-cli:2026.09.0` image at build time.
