ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64
ARG BUILDPLATFORM
ARG HA_CLI_VERSION=2026.09.0
ARG RIPWIRE_VERSION=0.6.2
ARG RTK_VERSION=0.49.0

FROM ghcr.io/home-assistant/${BUILD_ARCH}-hassio-cli:${HA_CLI_VERSION} AS ha_cli

FROM --platform=${BUILDPLATFORM} debian:bookworm-slim AS developer_tools

ARG BUILD_ARCH
ARG RIPWIRE_VERSION
ARG RTK_VERSION

RUN set -eux; \
    apt-get update; \
    apt-get install --no-install-recommends -y ca-certificates curl tar; \
    rm -rf /var/lib/apt/lists/*; \
    case "${BUILD_ARCH}" in \
        amd64) \
            ripwire_arch=x64; \
            ripwire_sha256=62ca4bf6dda09a23fe5829489232e64445ac80f42e51017614e31e201cc92b5a; \
            rtk_arch=x86_64-unknown-linux-musl; \
            rtk_sha256=7278231dfd7e6a730a4ab7f847b195bcf02289c2d57622b0dab75a6411100c8f \
            ;; \
        aarch64) \
            ripwire_arch=arm64; \
            ripwire_sha256=99754cfcfa2ec9cb51582e74cbd9fece6d8dce3523fc263881f278c56fd4d34a; \
            rtk_arch=aarch64-unknown-linux-gnu; \
            rtk_sha256=c8ea4b6560841e73157c134fd4a3293914c6ede42e786ee985cf491fde691ba7 \
            ;; \
        *) echo "Unsupported Home Assistant architecture: ${BUILD_ARCH}" >&2; exit 1 ;; \
    esac; \
    mkdir -p /tmp/ripwire /tmp/rtk /out/ripwire-skills; \
    curl -fsSLo /tmp/ripwire.tar.gz "https://github.com/redhat-et/ripwire/releases/download/v${RIPWIRE_VERSION}/ripwire-${RIPWIRE_VERSION}-linux-${ripwire_arch}.tar.gz"; \
    echo "${ripwire_sha256}  /tmp/ripwire.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/ripwire.tar.gz --strip-components=1 -C /tmp/ripwire; \
    install -m 0755 /tmp/ripwire/ripwire /out/ripwire; \
    cp -a /tmp/ripwire/skills/. /out/ripwire-skills/; \
    curl -fsSLo /tmp/rtk.tar.gz "https://github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}/rtk-${rtk_arch}.tar.gz"; \
    echo "${rtk_sha256}  /tmp/rtk.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/rtk.tar.gz -C /tmp/rtk; \
    install -m 0755 /tmp/rtk/rtk /out/rtk; \
    rm -rf /tmp/ripwire /tmp/rtk /tmp/ripwire.tar.gz /tmp/rtk.tar.gz

FROM nousresearch/hermes-agent:v2026.9.24 AS hermes_assets

FROM nousresearch/hermes-agent:v2026.9.24

ARG BUILD_VERSION
ARG BUILD_ARCH

COPY --from=ha_cli /usr/bin/ha /usr/local/bin/ha
COPY --from=developer_tools /out/ripwire /usr/local/bin/ripwire
COPY --from=developer_tools /out/rtk /usr/local/bin/rtk
COPY --from=developer_tools /out/ripwire-skills /opt/hermes/ripwire-skills
COPY --chmod=0755 install-ripwire-skills.sh /usr/local/lib/install-ripwire-skills.sh
COPY --chmod=0755 025-hermes-command-link /etc/cont-init.d/025-hermes-command-link
COPY --chmod=0755 03-ripwire-skills /etc/cont-init.d/03-ripwire-skills
COPY --chmod=0755 ingress-prefix-proxy.py /usr/local/lib/hermes-ingress-prefix-proxy.py
COPY --chmod=0755 ingress-prefix-proxy /etc/services.d/hermes-ingress-prefix-proxy/run
COPY plugins/ha-terminal /opt/hermes/plugins/ha-terminal
COPY --from=hermes_assets /opt/hermes/node_modules/@xterm/xterm/lib/xterm.js /opt/hermes/plugins/ha-terminal/dashboard/dist/xterm.js
COPY --from=hermes_assets /opt/hermes/node_modules/@xterm/xterm/css/xterm.css /opt/hermes/plugins/ha-terminal/dashboard/dist/xterm.css
COPY --from=hermes_assets /opt/hermes/node_modules/@xterm/addon-fit/lib/addon-fit.js /opt/hermes/plugins/ha-terminal/dashboard/dist/xterm-fit.js

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["gateway", "run"]
