# Hermes Agent Home Assistant Add-on

![Hermes Agent Home Assistant Add-on](hermes_agent/logo.png)

Home Assistant add-on repository for running Hermes Agent inside Home Assistant.

GitHub repository:
- `https://github.com/akm0d/ha-hermes-addon`

## Install in Home Assistant

1. Open Home Assistant.
2. Go to `Settings -> Add-ons -> Add-on Store`.
3. Open the three-dot menu and choose `Repositories`.
4. Add this repository URL:
   - `https://github.com/akm0d/ha-hermes-addon`
5. Refresh the Add-on Store if needed.
6. Open the `Hermes Agent` add-on.
7. Click `Install`.

## First start

1. Open the add-on Configuration page and edit the native Hermes YAML in `config_yaml`.
2. Start the add-on and check its log for gateway and dashboard startup.
3. Use the add-on Open Web UI button for the Hermes dashboard through Home Assistant ingress.
4. Configure Open WebUI to use TCP port `8642` for Hermes' OpenAI-compatible API.

## Notes

- Supported architectures: `amd64`, `aarch64`
- Hermes state is stored in Home Assistant's persistent add-on data mount at `/opt/data`
- The Hermes OpenAI-compatible API is exposed on TCP port `8642`
- The Hermes dashboard is available only through Home Assistant ingress; TCP port `9119` is not host-exposed
- Native `/opt/data/config.yaml` is authoritative and is mirrored to the raw `config_yaml` editor
- The official Home Assistant CLI is available to Hermes with the manifest's narrowly scoped Supervisor permissions; no second token is stored

## Add-on docs

Detailed add-on options are documented in:
- `hermes_agent/DOCS.md`
