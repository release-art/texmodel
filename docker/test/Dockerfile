# The image `pytest -m tex` runs in: the published reference image plus the TeX packages it does not carry yet.
# Delete a package here once the base image (proofpress, docker/texlive-packages.txt) has it.
#
#   bin/test-image.sh                      # builds texmodel-test
#   TEXMODEL_TEST_IMAGE=texmodel-test pdm run pytest -m tex
#
# BASE can be a digest (--build-arg BASE=releaseart/lualatex-python@sha256:...) to pin it. tlmgr already points at the base
# image's frozen TeX Live 2025 mirror, so nothing here chooses a repository.
ARG BASE=releaseart/lualatex-python:latest
FROM ${BASE}
# The mirror drops a download now and then and tlmgr carries on without the package, so retry, then check the files exist.
RUN for i in 1 2 3; do \
      tlmgr install tagpdf enumitem hyphenat anyfontsize pdfrender tikzfill && break || { [ "$i" = 3 ] && exit 1; sleep 15; }; \
    done \
 && fmtutil-sys --byfmt lualatex >/dev/null \
 && for f in tagpdf-base.sty enumitem.sty hyphenat.sty anyfontsize.sty pdfrender.sty tikzfill.image.sty; do \
      kpsewhich "$f" >/dev/null || { echo "missing after install: $f" >&2; exit 1; }; \
    done
