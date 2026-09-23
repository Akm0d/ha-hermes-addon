ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64
ARG HA_CLI_VERSION=2026.09.0

FROM ghcr.io/home-assistant/${BUILD_ARCH}-hassio-cli:${HA_CLI_VERSION} AS ha_cli

FROM nousresearch/hermes-agent:v2026.9.21

ARG BUILD_VERSION
ARG BUILD_ARCH

COPY --from=ha_cli /usr/bin/ha /usr/local/bin/ha
COPY --chmod=0755 ha-environment.py /usr/local/lib/hermes-ha-environment.py
COPY --chmod=0755 02-ha-environment /etc/cont-init.d/02-ha-environment
COPY --chmod=0755 ingress-prefix-proxy.py /usr/local/lib/hermes-ingress-prefix-proxy.py
COPY --chmod=0755 ingress-prefix-proxy /etc/services.d/hermes-ingress-prefix-proxy/run

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["gateway", "run"]
