#!/usr/bin/env bash
#
# Create the west workspace around this repository (west init -l) and fetch
# Zephyr (west.yml) if that has not happened yet. Runs as postCreateCommand
# of the dev container / GitHub Codespaces and before every build task.

set -e

if ! west topdir >/dev/null 2>&1; then
    echo 'West workspace not initialized; initializing it.'
    west init -l .
fi

if ! west list zephyr >/dev/null 2>&1; then
    echo 'Zephyr checkout not ready; fetching dependencies.'
    # Only the pinned revisions, without history: faster in Codespaces and CI
    west update --narrow --fetch-opt=--depth=1
fi
