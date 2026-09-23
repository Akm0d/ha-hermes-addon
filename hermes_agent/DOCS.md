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

The Configuration page intentionally has only two options:

- `enable_ha_cli`: exposes the official `ha` executable to Hermes when enabled. It is disabled by default.
- `config_yaml`: the complete native Hermes YAML configuration.

At every app start, the add-on validates that `config_yaml` is YAML whose document root is a mapping, then atomically writes it to `/opt/data/config.yaml` before Hermes' own initialization runs. The raw YAML text is preserved rather than translated into Home Assistant fields.

Home Assistant options are authoritative at startup. Hermes may change `config.yaml` while running, but the next app restart replaces it with `config_yaml`; there is no bidirectional synchronization.

Saving a changed options file is watched by an upstream-s6-supervised helper, which requests a normal Supervisor self-restart. It records the current checksum before watching and only requests one restart for a changed options file; writes to `/opt/data/config.yaml` do not trigger it.

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

The manifest requests the static Supervisor permissions `hassio_api: true` and `hassio_role: manager`. This lets the official Home Assistant CLI use the injected `SUPERVISOR_TOKEN` with the `supervisor` endpoint when `enable_ha_cli` is enabled.

The toggle is an application-level execution gate, not a permission change: Home Assistant still injects the manifest-granted token into the container while the app runs. When disabled, the real CLI binary is root-only and the `ha` command refuses execution; when enabled, it is executable by the normal non-root Hermes user. The add-on never creates or persists another Supervisor token.

`ha supervisor info` must be verified in a real Home Assistant OS environment. A normal Docker container does not provide the Supervisor endpoint or token.

If you want the full upstream setup flow, install notes, and provider details, see the official Hermes quickstart: https://hermes-agent.nousresearch.com/docs/getting-started/quickstart.

## Notes

- This add-on pins Hermes to `v2026.9.21`.
- Supported Home Assistant architectures are `amd64` and `aarch64`.
- There is no Home Assistant ingress UI, web terminal, model/provider option, or API-key option.
- The official Home Assistant CLI is copied from the pinned `ghcr.io/home-assistant/<arch>-hassio-cli:2026.09.0` image at build time.
