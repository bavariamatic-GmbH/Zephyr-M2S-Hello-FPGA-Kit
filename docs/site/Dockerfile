# syntax=docker/dockerfile:1.7
#
# Documentation tools for the project web page (Sphinx, Graphviz).
# Kept out of the firmware image (../../Dockerfile), which only holds what the
# Zephyr build needs. Used by the "docs" service in compose.yaml (VS Code
# tasks "Docs: ...") and by .github/workflows/docs.yml.

# Same pinned base image as the firmware image
FROM --platform=linux/amd64 python:3.12.15-slim-bookworm@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d

ARG DEBIAN_FRONTEND=noninteractive

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends graphviz \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /workspace
EXPOSE 8000

CMD ["sphinx-build", "-W", "--keep-going", "-b", "html", "docs/site", "docs/site/_build/html"]
