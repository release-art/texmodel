r"""calc: Arithmetic in lengths and counters. Loaded with `Package.require`; it declares no commands.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.package import Package

package = Package("calc", prefix="", adopted=True)
