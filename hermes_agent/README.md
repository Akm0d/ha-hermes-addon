# Hermes Agent Add-on

![Hermes Agent Home Assistant Add-on](logo.png)

Run Hermes Agent inside Home Assistant with a native add-on wrapper around the official upstream image.

Highlights:
- Hermes OpenAI-compatible API exposed on TCP port `8642`
- Home Assistant app-network API endpoint: `http://ab25b854-hermes-agent:8642/v1`
- persistent Hermes state stored at its normal Docker home, `/opt/data`
- bundled `ripwire`, `rg`, and `rtk` developer CLIs for Hermes agents and the dashboard Terminal
- support for `amd64` and `aarch64`
- pinned to `nousresearch/hermes-agent:v2026.9.24`
