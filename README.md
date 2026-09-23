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

1. Configure Hermes directly under its persistent home, `/opt/data`, following the upstream Hermes documentation.
2. Start the add-on.
3. Check the add-on log for Hermes gateway startup.
4. Configure Open WebUI to reach the Home Assistant host on TCP port `8642`.

## Notes

- Supported architectures: `amd64`, `aarch64`
- Hermes state is stored in Home Assistant's persistent add-on data mount at `/opt/data`
- The Hermes OpenAI-compatible API is exposed on TCP port `8642`
- There is no Home Assistant ingress dashboard or web terminal
- Model/provider and API-key configuration remain Hermes runtime configuration, not add-on options

## Add-on docs

Detailed add-on options are documented in:
- `hermes_agent/DOCS.md`
