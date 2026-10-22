r"""hyphenat: Hyphenation control. Loaded with `Package.require`; its commands are not declared.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.package import Package

package = Package("hyphenat", prefix="", adopted=True)
