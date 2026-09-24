# AGENTS.md

## Repo shape
- This repo is a Home Assistant add-on repository, not the Hermes source repo.
- Root metadata is `repository.yaml`.
- The only add-on currently present is `hermes_agent/`.

## Add-on metadata and startup
- Add-on metadata lives in `hermes_agent/config.yaml`.
- Image build is `hermes_agent/Dockerfile`.
- The add-on retains the official Hermes image ENTRYPOINT and supplies `CMD ["gateway", "run"]`; upstream routes this to `hermes gateway run`.
- User-facing add-on docs are `hermes_agent/DOCS.md`; keep them aligned with `config.yaml`.

## Runtime assumptions that matter
- The add-on wraps a versioned official upstream image `nousresearch/hermes-agent:vYYYY.M.D`; do not switch to `latest`.
- Supported Home Assistant architectures are only `amd64` and `aarch64`.
- Home Assistant provides its persistent data mount at `/opt/data`, Hermes' normal Docker home (`HERMES_HOME`).
- Hermes owns all state and runtime configuration under `/opt/data`; this add-on must not translate Home Assistant options into Hermes configuration.
- The OpenAI-compatible API is exposed directly on TCP port `8642`, and authenticated Hermes A2A is exposed on TCP port `9900`; the dashboard is reached through Home Assistant ingress on container port `9119` via a focused prefix adapter, with no nginx or separate terminal service. The native `ha-terminal` dashboard plugin intentionally grants dashboard users a shell in the container.

## Editing rules for this repo
- Home Assistant options are limited to the generated `api_server_key` integration secret; do not add translated Home Assistant, model, provider, or other Hermes runtime configuration fields.
- If add-on behavior or its exposed port changes, update `hermes_agent/DOCS.md`.

## Verification
- Build the wrapper image from the add-on directory:
  - `docker build --platform linux/amd64 -t ha-hermes-addon-test:local .`
  - run from `hermes_agent/`
- Local container smoke test from the repo root mounts a temporary directory at `/opt/data`, maps port `8642`, and verifies the gateway logs.
- There is no verified CI workflow in this repo yet; do not assume lint/test automation exists.

## Current known gaps
- Real Home Assistant port exposure and Open WebUI connectivity still need validation in a live Home Assistant environment.
