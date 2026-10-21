import pathlib
import sys

import pytest

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def acme():
    """The fixture package (tests/fixtures/acme_cards), imported once."""
    sys.path.insert(0, str(FIXTURES))
    try:
        import acme_cards  # pyright: ignore[reportMissingImports]
    finally:
        sys.path.remove(str(FIXTURES))
    return acme_cards
