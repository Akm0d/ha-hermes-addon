ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64
ARG HA_CLI_VERSION=2026.09.0

FROM ghcr.io/home-assistant/${BUILD_ARCH}-hassio-cli:${HA_CLI_VERSION} AS ha_cli

FROM nousresearch/hermes-agent:v2026.9.21

ARG BUILD_VERSION
ARG BUILD_ARCH

COPY --from=ha_cli /usr/bin/ha /usr/local/lib/hermes-ha-cli/ha
COPY --chmod=0755 ha-options.py /usr/local/lib/hermes-ha-options.py
COPY --chmod=0755 ha-cli /opt/hermes/bin/ha
COPY --chmod=0755 00-ha-options /etc/cont-init.d/00-ha-options

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["gateway", "run"]
