#!/usr/bin/env bash

set -e

# The repository root is the Zephyr application (I2C + SPI demo).
APP=.
BOARD_TARGET=m2s_hello_fpga_kit/m2s010

ensure_workspace() {
    if ! west topdir >/dev/null 2>&1; then
        echo 'Initializing West workspace.'
        west init -l .
    fi
}

# build_firmware <build-dir> <board> [west build options...]
build_firmware() {
    local build_dir=$1 board=$2
    shift 2
    bash .vscode/ensure-west-workspace.sh
    echo "Building target firmware for ${board} into ${build_dir}."
    west build "$@" -b "$board" -s "$APP" -d "$build_dir"
}

# Project web page (docs/site) through the "docs" service of compose.yaml.
# Needs Docker: works with VS Code on a Linux host, not inside the dev
# container (no Docker there).
need_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo 'Docker is not available here. Inside the dev container, run the "Docs" actions' >&2
        echo 'from VS Code on the host, or open a terminal on the host:' >&2
        echo '    docker compose up --build docs' >&2
        exit 1
    fi
}

case "${1:-}" in
    'Docs: Live preview')
        need_docker
        docker compose up --build --detach docs
        echo 'Waiting for http://localhost:8000 (first build takes a minute).'
        for _ in $(seq 1 180); do
            curl -fs -o /dev/null http://localhost:8000 && break
            sleep 1
        done
        echo 'Live preview on http://localhost:8000, rebuilt on every change.'
        echo 'Log follows; Ctrl+C ends the log, "Docs: Stop preview" stops the preview.'
        docker compose logs --follow --tail 20 docs
        ;;
    'Docs: Build (strict, like CI)')
        need_docker
        docker compose run --rm --build --no-deps docs \
            sphinx-build -E -W --keep-going -b html docs/site docs/site/_build/html
        echo 'Page in docs/site/_build/html/index.html'
        ;;
    'Docs: Stop preview')
        need_docker
        docker compose stop docs
        ;;
    'Initialize + update'|'Update dependencies')
        ensure_workspace
        echo 'Updating West dependencies.'
        west update
        ;;
    'Build firmware')
        build_firmware build "$BOARD_TARGET"
        ;;
    'Clean and Build')
        build_firmware build "$BOARD_TARGET" -p always
        ;;
    'Clean')
        echo 'Cleaning build directories.'
        rm -rf build
        ;;
    *)
        echo "Unknown West workspace action: ${1:-}" >&2
        exit 2
        ;;
esac
