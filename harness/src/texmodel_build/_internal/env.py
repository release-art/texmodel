"""The hermetic environment a compile runs in (C3): only what TeX needs, nothing inherited by accident."""

import os
from collections.abc import Sequence


def build_env(
    *,
    roots: Sequence[str],
    fonts: Sequence[str] = (),
    epoch: int | None = None,
    cache: str | None = None,
    inherit: Sequence[str] = (),
) -> dict[str, str]:
    """`roots` are paths as the compiler sees them (container paths in a container).

    A trailing separator in the search variables keeps the default search path after the roots.
    """
    search = os.pathsep.join([".", *roots]) + os.pathsep
    rooted = os.pathsep.join(roots) + os.pathsep if roots else ""
    env = {
        "TEXINPUTS": search,
        "OPENTYPEFONTS": rooted,
        "TTFONTS": rooted,
        # Logs are parsed, so never hard-wrapped.
        "max_print_line": "10000",
        "error_line": "254",
        "half_error_line": "238",
    }
    if rooted == "":
        del env["OPENTYPEFONTS"], env["TTFONTS"]
    if fonts:
        env["OSFONTDIR"] = os.pathsep.join(fonts)  # families a document names but never paths
    if cache:
        env["TEXMFVAR"] = env["TEXMFCACHE"] = cache
    if epoch is not None:
        env["SOURCE_DATE_EPOCH"] = str(epoch)
        env["FORCE_SOURCE_DATE"] = "1"
    for name in inherit:
        if name in os.environ:
            env[name] = os.environ[name]
    return env
