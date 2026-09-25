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

1. Start the add-on and check its log for gateway and dashboard startup.
2. Use the add-on Open Web UI button for the Hermes dashboard through Home Assistant ingress.
3. Use the dashboard's **Terminal** tab for interactive Hermes setup and container administration.
4. Retrieve the generated OpenAI-compatible API bearer key from `/opt/data/.env` only when needed; it is not shown in Home Assistant Options.

## Notes

- Supported architectures: `amd64`, `aarch64`
- Hermes state is stored in Home Assistant's persistent add-on data mount at `/opt/data`
- User-installed Hermes plugins live in `/opt/data/plugins/` and survive add-on image upgrades; `/opt/hermes` remains image-owned.
- The Hermes OpenAI-compatible API is exposed on TCP port `8642`
- Authenticated Hermes A2A is exposed on TCP port `9900`
- The Hermes dashboard is available only through Home Assistant ingress; TCP port `9119` is not host-exposed
- Hermes owns its native `/opt/data/config.yaml`; Home Assistant does not mirror or translate it
- The official Home Assistant CLI is available to Hermes with the manifest's narrowly scoped Supervisor permissions; no second token is stored
- Dashboard access intentionally grants interactive shell access to the Hermes container through the native terminal plugin
- The dashboard Terminal and Hermes agents have `ripwire`, `rg`, and `rtk` available on `PATH`

## OpenAI-compatible API

For Home Assistant integrations running inside the Home Assistant app network, use:

```text
http://ab25b854-hermes-agent:8642/v1
```

Example configuration:

```text
Base URL: http://ab25b854-hermes-agent:8642/v1
Model: hermes-agent
Authentication: Bearer API_SERVER_KEY
```

This is the internal app-network endpoint; `localhost:8642` and `127.0.0.1:8642` from Home Assistant Core refer to the Core container, not Hermes. For trusted clients that can reach the published port, use `http://<home-assistant-host>:8642/v1` instead.

This endpoint works with Local OpenAI LLM, Open WebUI, and other OpenAI-compatible clients. Client-supplied OpenAI tools are not necessarily equivalent to Hermes-native tools.

`API_SERVER_KEY` is a secret bearer credential stored in `/opt/data/.env`. An administrator can retrieve it from the dashboard Terminal when necessary:

```bash
grep '^API_SERVER_KEY=' /opt/data/.env
```

Treat the output as a secret; do not paste it into logs or chats.

## Add-on docs

Detailed add-on documentation is in:
- `hermes_agent/DOCS.md`
