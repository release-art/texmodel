"""Typed document-family models rendered to TeX."""

import logging

from .compiler import Compiler
from .result import CompileResult

__all__ = ["CompileResult", "Compiler"]

# A library never configures logging or prints (E5); the application decides.
logging.getLogger(__name__).addHandler(logging.NullHandler())
