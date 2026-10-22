"""The smallest package: one command with an inline body."""

from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("hello", prefix="hi", version="1.0.0", date="2026/10/22", description="The smallest package")


@pkg.command
class Greet(Command):
    """Greet someone by name."""

    body = r"\par Hello, #name!\par"

    name: Text


# Text is escaped, so awkward names are safe.
documents = {"hello": pkg.document(Greet("World"), Greet("R&D #1 (50% off)"))}
