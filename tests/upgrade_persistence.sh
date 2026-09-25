#!/bin/sh

# Recreate the add-on container with a shared data volume.  This deliberately
# tests image replacement, not merely a restart of one container.
set -eu

: "${PREVIOUS_IMAGE:?set PREVIOUS_IMAGE to the current add-on image}"
: "${UPGRADE_IMAGE:?set UPGRADE_IMAGE to the replacement add-on image}"

volume="ha-hermes-upgrade-test-$$"
old_container="ha-hermes-old-$$"
new_container="ha-hermes-new-$$"

cleanup() {
    docker rm -f "${old_container}" "${new_container}" >/dev/null 2>&1 || true
    docker volume rm "${volume}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker volume create "${volume}" >/dev/null

# Model a user-installed dashboard plugin plus representative Hermes state.
docker run --rm -v "${volume}:/opt/data" --entrypoint /bin/sh "${PREVIOUS_IMAGE}" -ceu '
    mkdir -p /opt/data/plugins/upgrade-sentinel/dashboard /opt/data/sessions /opt/data/memories
    printf "%s\n" "name: upgrade-sentinel" > /opt/data/plugins/upgrade-sentinel/plugin.yaml
    printf "%s\n" "{\"name\": \"upgrade-sentinel\"}" > /opt/data/plugins/upgrade-sentinel/dashboard/manifest.json
    printf "%s\n" "user-session" > /opt/data/sessions/upgrade-sentinel.txt
    printf "%s\n" "memory" > /opt/data/memories/upgrade-sentinel.md
    printf "%s\n" "UPGRADE_TEST_STATE=preserved" > /opt/data/.env
'

docker run -d --name "${old_container}" -v "${volume}:/opt/data" "${PREVIOUS_IMAGE}" gateway run >/dev/null
sleep 5
docker exec "${old_container}" /opt/hermes/.venv/bin/python -c "from hermes_cli.web_server_dashboard import _discover_dashboard_plugins; names = {plugin[\"name\"] for plugin in _discover_dashboard_plugins()}; assert {\"upgrade-sentinel\", \"ha-terminal\"} <= names, names"
api_key_hash=$(docker exec "${old_container}" /bin/sh -ceu 'key=$(sed -n "s/^API_SERVER_KEY=//p" /opt/data/.env); test -n "$key"; printf %s "$key" | sha256sum | awk "{print \$1}"')
docker rm -f "${old_container}" >/dev/null

docker run -d --name "${new_container}" -v "${volume}:/opt/data" "${UPGRADE_IMAGE}" gateway run >/dev/null
sleep 8

docker exec "${new_container}" /bin/sh -ceu '
    test -f /opt/data/plugins/upgrade-sentinel/plugin.yaml
    test -f /opt/data/plugins/upgrade-sentinel/dashboard/manifest.json
    test -f /opt/data/sessions/upgrade-sentinel.txt
    test -f /opt/data/memories/upgrade-sentinel.md
    grep -qx "UPGRADE_TEST_STATE=preserved" /opt/data/.env
    test -f /opt/hermes/plugins/ha-terminal/dashboard/manifest.json
    test -L /opt/data/.local/bin/hermes
    test "$(readlink /opt/data/.local/bin/hermes)" = /opt/hermes/.venv/bin/hermes
    /opt/hermes/.venv/bin/python -c "from hermes_cli.web_server_dashboard import _discover_dashboard_plugins; names = {plugin[\"name\"] for plugin in _discover_dashboard_plugins()}; assert {\"upgrade-sentinel\", \"ha-terminal\"} <= names, names"
    hermes doctor
'
test "${api_key_hash}" = "$(docker exec "${new_container}" /bin/sh -ceu 'key=$(sed -n "s/^API_SERVER_KEY=//p" /opt/data/.env); test -n "$key"; printf %s "$key" | sha256sum | awk "{print \$1}"')"

plugin_hash=$(docker exec "${new_container}" sha256sum /opt/data/plugins/upgrade-sentinel/plugin.yaml | awk '{print $1}')
docker restart "${new_container}" >/dev/null
sleep 5
docker exec "${new_container}" /bin/sh -ceu '
    test -f /opt/data/plugins/upgrade-sentinel/plugin.yaml
    test -f /opt/hermes/plugins/ha-terminal/dashboard/manifest.json
    test -L /opt/data/.local/bin/hermes
'
test "${plugin_hash}" = "$(docker exec "${new_container}" sha256sum /opt/data/plugins/upgrade-sentinel/plugin.yaml | awk '{print $1}')"
