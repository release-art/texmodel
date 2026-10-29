r"""Extensions: opinionated helpers built on the core, one module each (`std` is the standard TeX headers).

- `kplate`: colours on the black plate only, tints that stay on it, and which plates a colour inks.
- `intent`: a PDF output intent (PDF/X, PDF/A): the `\\DocumentMetadata` keys and the ICC condition registration.
- `printpage`: a print page (trim, bleed, margins) as geometry and PDF page boxes, edge by edge.
- `spot`: a named plate on the press (a varnish, a foil) with a CMYK proxy, and tints of it.
- `recorded`: a value only the whole document knows (the widest label), carried between runs, and its folds.
- `fit`: a short line set to fit a band at sizes shared across the document, and the rule in Python.
- `colourspace`: a colour with a print and a screen build under one name, and `colour_of`, the name of a colour value.
"""
