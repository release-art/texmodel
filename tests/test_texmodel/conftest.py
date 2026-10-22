import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="session")
def acme():
    """The fixture package (tests/fixtures/acme_cards), imported once."""
    with pytest.MonkeyPatch.context() as monkeypatch:  # session scope, so not the function-scoped fixture
        monkeypatch.syspath_prepend(str(FIXTURES))
        import acme_cards  # pyright: ignore[reportMissingImports]
    return acme_cards
