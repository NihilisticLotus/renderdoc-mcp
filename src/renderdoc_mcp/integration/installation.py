"""Local RenderDoc installation discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True, slots=True)
class RenderDocInstallation:
    root: Path
    renderdoccmd: Path
    qrenderdoc: Path | None
    renderdoc_dll: Path | None
    runtime_family: str = "renderdoc"

    @property
    def command(self) -> Path:
        """Replay CLI, regardless of the runtime's branded filename."""
        return self.renderdoccmd

    @property
    def gui(self) -> Path | None:
        """GUI executable, regardless of the runtime's branded filename."""
        return self.qrenderdoc

    @property
    def runtime_dll(self) -> Path | None:
        """Core replay DLL, regardless of the runtime's branded filename."""
        return self.renderdoc_dll


def _candidate_roots() -> list[tuple[Path, str | None]]:
    candidates: list[tuple[Path, str | None]] = []

    # An explicit RenderTest root wins over the legacy RENDERDOC_PATH. This
    # keeps an old installation available while allowing side-by-side runtimes.
    test_root = os.environ.get("RENDERTEST_PATH")
    if test_root:
        candidates.append((Path(test_root), "rendertest"))

    doc_root = os.environ.get("RENDERDOC_PATH")
    if doc_root:
        candidates.append((Path(doc_root), None))

    candidates.append((Path(r"C:\Program Files\RenderDoc"), "renderdoc"))
    candidates.append((Path(r"C:\Program Files (x86)\RenderDoc"), "renderdoc"))

    return candidates


def _from_root(root: Path, family: str | None) -> RenderDocInstallation | None:
    if family == "rendertest":
        cmd = root / "rendertestcmd.exe"
        if not cmd.is_file():
            raise FileNotFoundError(
                "RENDERTEST_PATH is set, but rendertestcmd.exe was not found under {}".format(root)
            )
        return RenderDocInstallation(
            root=root,
            renderdoccmd=cmd,
            qrenderdoc=(root / "qrendertest.exe") if (root / "qrendertest.exe").is_file() else None,
            renderdoc_dll=(root / "rendertest.dll") if (root / "rendertest.dll").is_file() else None,
            runtime_family="rendertest",
        )

    # Preserve the legacy default when a directory contains both installations.
    cmd = root / "renderdoccmd.exe"
    if cmd.is_file():
        return RenderDocInstallation(
            root=root,
            renderdoccmd=cmd,
            qrenderdoc=(root / "qrenderdoc.exe") if (root / "qrenderdoc.exe").is_file() else None,
            renderdoc_dll=(root / "renderdoc.dll") if (root / "renderdoc.dll").is_file() else None,
            runtime_family="renderdoc",
        )

    # New names are also accepted through RENDERDOC_PATH for a single-runtime
    # directory; ambiguous side-by-side directories should use RENDERTEST_PATH.
    cmd = root / "rendertestcmd.exe"
    if cmd.is_file():
        return RenderDocInstallation(
            root=root,
            renderdoccmd=cmd,
            qrenderdoc=(root / "qrendertest.exe") if (root / "qrendertest.exe").is_file() else None,
            renderdoc_dll=(root / "rendertest.dll") if (root / "rendertest.dll").is_file() else None,
            runtime_family="rendertest",
        )
    return None


def discover_installation() -> RenderDocInstallation:
    for root, family in _candidate_roots():
        installation = _from_root(root, family)
        if installation is not None:
            return installation

    raise FileNotFoundError(
        "Could not find a local RenderDoc installation. Set RENDERDOC_PATH if needed."
    )
