r"""anyfontsize: Any font size. Loaded with `Package.require`; it declares no commands.

A header (the package is adopted): it declares the interface, `texmodel` writes calls and never the package."""

from texmodel.package import Package

package = Package("anyfontsize", prefix="", adopted=True)
