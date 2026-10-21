PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "${PROJECT_ROOT}"

DIRS=(
    "src"
    "harness"
    "tests"
)

pdm run ruff format "${DIRS[@]}"
pdm run ruff check --fix  "${DIRS[@]}"
pdm run pyright
pdm run lint-imports
