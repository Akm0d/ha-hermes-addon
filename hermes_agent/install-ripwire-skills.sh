#!/bin/sh

set -eu

source_dir=/opt/hermes/ripwire-skills
hermes_home=${HERMES_HOME:-/opt/data}
target_dir=${hermes_home}/skills

if [ ! -d "${source_dir}" ]; then
    echo "Ripwire skill payload is missing: ${source_dir}" >&2
    exit 1
fi

if [ ! -d "${target_dir}" ]; then
    mkdir -p "${target_dir}"
    chown hermes:hermes "${target_dir}"
fi

for source_skill in "${source_dir}"/*; do
    [ -d "${source_skill}" ] || continue

    skill_name=$(basename "${source_skill}")
    target_skill=${target_dir}/${skill_name}
    if [ -e "${target_skill}" ] || [ -L "${target_skill}" ]; then
        echo "[ripwire] preserving existing skill: ${skill_name}"
        continue
    fi

    cp -a "${source_skill}" "${target_skill}"
    chown -R hermes:hermes "${target_skill}"
    echo "[ripwire] installed skill: ${skill_name}"
done
