"""Compile and verify LaTeX built from texmodel: a thin `latexmk` driver, typed log diagnostics, verifier plugins."""

import logging

from .compiler import Compiler
from .result import CompileResult

__all__ = ["CompileResult", "Compiler"]

logging.getLogger(__name__).addHandler(logging.NullHandler())
