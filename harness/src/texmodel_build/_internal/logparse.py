"""Parse a LuaTeX/LaTeX log into typed diagnostics (C2).

The compile driver runs with `max_print_line` raised, so log lines are never hard-wrapped, and with
`-file-line-error`, so most errors read `file:line: message`; a few (a missing file) still read `! message`.
"""

import dataclasses
import re
from collections.abc import Callable, Sequence

from ..diagnostics import (
    Diagnostic,
    DocumentRefusal,
    Measure,
    Measurement,
    MissingCharacter,
    MissingFile,
    OverfullBox,
    PackageError,
    PackageWarning,
    RerunNeeded,
    TexError,
    UndefinedControlSequence,
    UndefinedReference,
    overset,
)

_LOC = re.compile(r"^(?P<file>[^\s:][^:]*):(?P<line>\d+): (?P<msg>.*)$")
_BANG = re.compile(r"^! (?P<msg>.*)$")
_CONTEXT = re.compile(r"^l\.(?P<line>\d+) (?P<text>.*)$")
_CS = re.compile(r"(\\[A-Za-z@]+|\\.)\s*$")
_MISSING_CHAR = re.compile(r"^Missing character: There is no .+ \(U\+(?P<cp>[0-9A-Fa-f]+)\) in font (?P<font>.+)!$")
_OVERFULL = re.compile(r"^Overfull \\(?P<dir>[hv])box \((?P<amount>[\d.]+)pt too (?:wide|high)\)(?P<rest>.*)$")
_FIRST_LINE = re.compile(r"lines? (\d+)")
_RERUN = re.compile(r"Rerun to get|Rerun LaTeX|Please \(re\)run|rerunfilecheck Warning: File .* has changed")
_UNDEFINED_REF = re.compile(
    r"LaTeX Warning: (?P<kind>Reference|Citation) `(?P<name>.+?)' on page \d+ undefined on input line (?P<line>\d+)"
)
_MISSING_FILE = re.compile(r"File `(?P<name>.+?)' not found")
_PACKAGE_ERROR = re.compile(r"Package (?P<package>\S+) Error:\s*(?P<rest>.*)$")
_PACKAGE_WARNING = re.compile(r"^Package (?P<package>\S+) Warning:\s*(?P<rest>.*)$")
_ON_LINE = re.compile(r"\s*on input line (?P<line>\d+)\.?$")
_PROBE = re.compile(r"^texmodel:probe:(?P<name>[^=\s]+)=(?P<value>.*)$")
_FIT_PROBE = re.compile(r"^fit\.(?P<item>.+)$")
_NEEDS_HAS = re.compile(r"^(?P<needs>[^/]+)/(?P<has>[^/]+)$")
_REFUSE = re.compile(r"^texmodel:refuse:(?P<reason>.*)$")
_PAGES = re.compile(r"Output written on .* \((?P<n>\d+) pages?, \d+ bytes\)")
# Consequences of an error already reported, not errors of their own.
_CONSEQUENCE = ("Emergency stop.", "==> Fatal error occurred")
_LOOKAHEAD = 15


def parse_log(text: str, measures: Sequence[Measure] = ()) -> tuple[Diagnostic, ...]:
    """Typed diagnostics; `measures` read a package's warnings as `Overset` (B2) besides the warning itself."""
    lines = text.splitlines()
    found: dict[tuple[object, ...], Diagnostic] = {}

    def add(diagnostic: Diagnostic) -> None:
        # The same finding repeats per pass and per occurrence; keep one with a count.
        key = tuple(v for k, v in sorted(dataclasses.asdict(diagnostic).items()) if k != "count") + (type(diagnostic),)
        seen = found.get(key)
        found[key] = dataclasses.replace(seen, count=seen.count + 1) if seen else diagnostic

    for i, line in enumerate(lines):
        if m := _LOC.match(line):
            _error(lines, i, m["msg"], m["file"], int(m["line"]), add)
        elif m := _BANG.match(line):
            _error(lines, i, m["msg"], None, _context(lines, i)[0], add)
        else:
            _note(lines, i, add)
    for found_one in list(found.values()):
        if isinstance(found_one, PackageWarning):
            for rule in measures:
                if rule.package == found_one.package and (m := rule.pattern.search(found_one.message)):
                    if over := overset(m["item"], m["needs"], m["has"], line=found_one.line):
                        add(over)
    return tuple(found.values())


def _note(lines: list[str], i: int, add: Callable[[Diagnostic], None]) -> None:
    """Lines that carry a finding without being an error message: missing glyphs, boxes, references, probes."""
    line = lines[i]
    if m := _MISSING_CHAR.match(line):
        font = m["font"].strip('"')
        cp = m["cp"].upper()
        add(MissingCharacter(message=f"no glyph for U+{cp} in {font}", font=font, codepoint=int(cp, 16)))
    elif m := _OVERFULL.match(line):
        first = _FIRST_LINE.search(m["rest"])
        add(
            OverfullBox(
                message=line, amount_pt=float(m["amount"]), direction=m["dir"], line=int(first[1]) if first else None
            )
        )
    elif m := _UNDEFINED_REF.search(line):
        message = f"{m['kind']} `{m['name']}' undefined"
        add(UndefinedReference(message=message, kind=m["kind"], name=m["name"], line=int(m["line"])))
    elif _RERUN.search(line):
        add(RerunNeeded(message="rerun needed"))
    elif m := _PROBE.match(line):
        _probe(m, add)
    elif m := _REFUSE.match(line):
        add(DocumentRefusal(message=m["reason"]))
    elif m := _PACKAGE_WARNING.match(line):
        package = m["package"]
        detail = [m["rest"].strip()]
        for following in lines[i + 1 : i + 1 + _LOOKAHEAD]:
            if not following.startswith(f"({package})"):
                break
            detail.append(following[len(package) + 2 :].strip())
        message = " ".join(d for d in detail if d)
        where = _ON_LINE.search(message)
        add(
            PackageWarning(
                message=_ON_LINE.sub("", message), package=package, line=int(where["line"]) if where else None
            )
        )


def _probe(m: re.Match[str], add: Callable[[Diagnostic], None]) -> None:
    """A probe is a `Measurement`; `fit.<item>=<needs>/<has>` that does not fit is also an `Overset` (B2)."""
    add(Measurement(message=m[0], name=m["name"], value=m["value"]))
    if (item := _FIT_PROBE.match(m["name"])) and (fit := _NEEDS_HAS.match(m["value"])):
        if over := overset(item["item"], fit["needs"], fit["has"]):
            add(over)


def page_count(text: str) -> int | None:
    m = _PAGES.search(text)
    return int(m["n"]) if m else None


def _context(lines: list[str], i: int) -> tuple[int | None, str]:
    """The `l.N <text>` line TeX prints after an error: the line number and the text up to the break."""
    for line in lines[i + 1 : i + 1 + _LOOKAHEAD]:
        if m := _CONTEXT.match(line):
            return int(m["line"]), m["text"]
    return None, ""


def _error(
    lines: list[str], i: int, msg: str, file: str | None, line: int | None, add: Callable[[Diagnostic], None]
) -> None:
    msg = msg.strip()
    if msg.startswith(_CONSEQUENCE):
        return
    if msg.startswith("Undefined control sequence"):
        top = lines[i + 1] if i + 1 < len(lines) else ""
        cs = _CS.search(
            top if top and not _CONTEXT.match(top) else _context(lines, i)[1]
        )  # `<argument> \name`, else `l.N`
        add(
            UndefinedControlSequence(
                message=f"undefined control sequence {cs[1] if cs else '?'}",
                name=cs[1] if cs else "",
                file=file,
                line=line,
            )
        )
    elif m := _MISSING_FILE.search(msg):
        add(MissingFile(message=f"file `{m['name']}' not found", name=m["name"], file=file, line=line))
    elif m := _PACKAGE_ERROR.search(msg):
        package = m["package"]
        detail = [m["rest"].strip()]
        for following in lines[i + 1 : i + 1 + _LOOKAHEAD]:
            if not following.startswith(f"({package})"):
                break
            detail.append(following[len(package) + 2 :].strip())
        add(PackageError(message=" ".join(d for d in detail if d), package=package, file=file, line=line))
    else:
        add(TexError(message=msg, file=file, line=line))
