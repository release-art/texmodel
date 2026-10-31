# Pictures

`texmodel.ext.graphics` places a picture with `\includegraphics` and a few opinions: a picture never distorts, always
says what it shows, and sits in a centred figure with its caption below. The blocks on this page run in order, as one
module.

```python
from texmodel.document import Document
from texmodel.ext.graphics import Crop, Figure, Picture
from texmodel.types import Length

logo = Picture("img/logo.png", alt="The logo: a blue wave", width=Length.expr(r"0.8\linewidth"))
assert logo.render() == r"\includegraphics[width=0.8\linewidth,alt=The logo: a blue wave]{img/logo.png}"

figure = Figure(logo, caption="The logo", label="fig:logo", placement="tbp")
assert figure.render().splitlines()[:2] == [r"\begin{figure}[tbp]", r"\centering"]
document = Document(figure.node())
```

- **Never distorted.** `width` and `height` together fit the picture into that box and keep its proportions
  (`keepaspectratio`); `scale` is a factor and cannot be combined with them (`TM-C034`). `rotate` is degrees
  counter-clockwise, `page` a page of a PDF, and `crop=Crop(left=, bottom=, right=, top=)` cuts the edges.
- **Always described.** `alt` is the text a tagged PDF and a screen reader give for the picture; a picture that says
  nothing is `decorative=True` (an `artifact` of the PDF). Neither or both is `TM-C033`. Text is escaped.
- **A checked path.** A `str`, a `PurePosixPath` or a `FilePath`; a character TeX reads as syntax is refused (`TM-C028`).
  A path from a macro is a `Macro`.
- **A figure** is `\begin{figure}[placement]`, `\centering`, the picture, `\caption[short]{caption}` and `\label{label}`;
  the placement is letters of `h`, `t`, `b`, `p` and `!` (`TM-C035`).

The document's package requires `graphicx` (`texmodel.std.graphicx`). `alt` and `artifact` need LaTeX 2024-11 or later.

```python
cropped = Picture("scan.pdf", alt="A scan", page=2, crop=Crop(top=Length("1cm")), rotate=90)
assert "clip,trim=0pt 0pt 0pt 1cm" in cropped.render()
```
