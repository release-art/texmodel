import texmodel


def test_imports():
    assert texmodel.__doc__


def test_library_logger_is_silent_by_default():
    import logging

    assert any(isinstance(h, logging.NullHandler) for h in logging.getLogger("texmodel").handlers)
