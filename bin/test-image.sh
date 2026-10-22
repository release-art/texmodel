#!/bin/sh
# Build the image the compile suite runs in (docker/test/Dockerfile); the name defaults to texmodel-test.
#   bin/test-image.sh && TEXMODEL_TEST_IMAGE=texmodel-test pdm run pytest -m tex
set -eu
cd "$(dirname "$0")/.."
exec docker build -t "${TEXMODEL_TEST_IMAGE:-texmodel-test}" "$@" docker/test
