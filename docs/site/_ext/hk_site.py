"""Sphinx extension for the project web page.

1. Before every build, copies the project's Markdown files and the proposed
   Zephyr board page into ``generated/`` (see ``hk_pages`` and
   ``hk_board_doc`` in conf.py). Links between copied files are kept as
   document links; links to other files of the repository point to GitHub.
   Files are only rewritten when their content changes, so sphinx-autobuild
   does not rebuild everything.

2. Provides simple versions of the Zephyr documentation directives and roles
   the board page uses (``zephyr:board``, ``zephyr:board-supported-hw``,
   ``zephyr:board-supported-runners``, ``zephyr-app-commands``,
   ``:zephyr:code-sample:``). Zephyr's own versions read the board files and
   the devicetree; these take the values from ``zephyr_preview`` in conf.py.
   The page is a preview: the real rendering is the one of the Zephyr docs
   build.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive, directives
from sphinx.domains import Domain
from sphinx.util import logging

log = logging.getLogger(__name__)

# [text](target) and ![alt](target); target without spaces, optional "title"
_INLINE_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(\s+\"[^\"]*\")?\)")
# [label]: target
_REF_LINK = re.compile(r"^(\s*\[[^\]]+\]:\s*)(\S+)(.*)$", re.MULTILINE)
_EXTERNAL = ("http://", "https://", "mailto:", "#")


# ---------------------------------------------------------------- generation

def _write_if_changed(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "b" if isinstance(data, bytes) else ""
    if path.exists():
        old = path.read_bytes() if mode else path.read_text(encoding="utf-8")
        if old == data:
            return
    if mode:
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8", newline="\n")


class _Rewriter:
    def __init__(self, app):
        cfg = app.config
        self.repo_root = Path(app.srcdir, cfg.hk_repo_root).resolve()
        self.out = Path(app.srcdir, "generated")
        self.blob = f"https://github.com/{cfg.hk_github_repo}/blob/{cfg.hk_github_branch}/"
        self.tree = f"https://github.com/{cfg.hk_github_repo}/tree/{cfg.hk_github_branch}/"
        self.raw = f"https://raw.githubusercontent.com/{cfg.hk_github_repo}/{cfg.hk_github_branch}/"
        # repository path -> path in generated/
        self.map = {src: dst for src, dst in cfg.hk_pages}
        board = cfg.hk_board_doc
        self.map[f"{board}/index.rst"] = "zephyr-board/index.rst"
        self.board = board

    def target(self, source: str, link: str, image: bool) -> str:
        if link.startswith(_EXTERNAL):
            return link
        path, _, anchor = link.partition("#")
        repo_path = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        if repo_path.startswith(".."):
            return link  # outside the repository (sibling repositories)
        anchor = f"#{anchor}" if anchor else ""
        if not image and repo_path in self.map:
            here = posixpath.dirname(self.map[source])
            rel = posixpath.relpath(self.map[repo_path], here or ".")
            return rel + anchor
        if image:
            return self.raw + repo_path
        base = self.tree if (self.repo_root / repo_path).is_dir() else self.blob
        return base + repo_path + anchor

    def markdown(self, source: str) -> str:
        text = (self.repo_root / source).read_text(encoding="utf-8")

        def inline(m):
            bang, label, link, title = m.groups()
            new = self.target(source, link, image=bool(bang))
            return f"{bang}[{label}]({new}{title or ''})"

        def ref(m):
            return m.group(1) + self.target(source, m.group(2), image=False) + m.group(3)

        # Leave fenced code blocks alone
        parts = re.split(r"(^```.*?^```)", text, flags=re.MULTILINE | re.DOTALL)
        for i in range(0, len(parts), 2):
            parts[i] = _REF_LINK.sub(ref, _INLINE_LINK.sub(inline, parts[i]))
        return "".join(parts)

    def generate(self, app) -> None:
        for source, dest in app.config.hk_pages:
            _write_if_changed(self.out / dest, self.markdown(source))
        self.board_page(app)

    def board_page(self, app) -> None:
        src = self.repo_root / self.board
        dst = self.out / "zephyr-board"
        for img in (src / "img").glob("*"):
            _write_if_changed(dst / "img" / img.name, img.read_bytes())
        text = (src / "index.rst").read_text(encoding="utf-8")
        title = app.config.zephyr_preview["full_name"]
        banner = (
            f"{'#' * len(title)}\n{title}\n{'#' * len(title)}\n\n"
            ".. admonition:: Preview\n"
            "   :class: hk-preview\n\n"
            "   This is the board page proposed for the Zephyr project\n"
            f"   (``{self.board}/index.rst`` in this repository). Zephyr-specific\n"
            "   directives are rendered by a simplified local extension; the boxes\n"
            "   generated from the board files look different in the Zephyr docs.\n"
            "   See :doc:`../zephyr-pr` for how to submit it.\n\n"
        )
        # Figures whose image is not there yet: show a placeholder instead of
        # failing the build (the Zephyr pull request needs the real image)
        def figure(m):
            indent, image, body = m.groups()
            if (src / image).exists():
                return m.group(0)
            caption = " ".join(line.strip() for line in body.splitlines()
                               if line.strip() and not line.strip().startswith(":"))
            return (f"{indent}.. admonition:: Screenshot missing\n"
                    f"{indent}   :class: warning\n\n"
                    f"{indent}   ``{image}`` is not in the repository yet: {caption}\n\n")

        # The figure line, its indented options and caption, and blank lines
        text = re.sub(r"^( *)\.\. figure:: (\S+)\n((?:\1 {3}.*\n|[ \t]*\n)*)", figure, text,
                      flags=re.MULTILINE)
        # Title first: in Zephyr it comes from the zephyr:board directive
        marker = ".. zephyr:board::"
        idx = text.index(marker)
        text = text[:idx] + banner + text[idx:]
        _write_if_changed(dst / "index.rst", text)


def _generate(app) -> None:
    _Rewriter(app).generate(app)


def _edit_link(app, pagename, templatename, context, doctree) -> None:
    """"Edit on GitHub" of a generated page opens the original file."""
    cfg = app.config
    originals = {f"generated/{posixpath.splitext(dst)[0]}": src for src, dst in cfg.hk_pages}
    originals["generated/zephyr-board/index"] = f"{cfg.hk_board_doc}/index.rst"
    if pagename in originals:
        meta = dict(context.get("meta") or {})
        meta["github_url"] = (f"https://github.com/{cfg.hk_github_repo}/blob/"
                              f"{cfg.hk_github_branch}/{originals[pagename]}")
        context["meta"] = meta


# ---------------------------------------------------------------- Zephyr directives

def _table(headers, rows, widths=None):
    table = nodes.table()
    tgroup = nodes.tgroup(cols=len(headers))
    table += tgroup
    for w in widths or [1] * len(headers):
        tgroup += nodes.colspec(colwidth=w)
    thead = nodes.thead()
    tgroup += thead
    row = nodes.row()
    for h in headers:
        row += nodes.entry("", nodes.paragraph(text=h))
    thead += row
    tbody = nodes.tbody()
    tgroup += tbody
    for r in rows:
        row = nodes.row()
        for cell in r:
            entry = nodes.entry()
            entry += nodes.paragraph(text=str(cell))
            row += entry
        tbody += row
    return table


class BoardDirective(Directive):
    required_arguments = 1

    def run(self):
        info = self.state.document.settings.env.config.zephyr_preview
        name = self.arguments[0]
        box = nodes.container(classes=["hk-board-card"])
        box += nodes.image(uri=f"img/{name}.webp", alt=info["full_name"], width="400px")
        box += _table(["Property", "Value"], [
            ("Name", info["full_name"]),
            ("Board target", info["target"]),
            ("Vendor", info["vendor"]),
            ("Architecture", info["arch"]),
            ("SoC", info["soc"]),
        ], [1, 3])
        return [box]


class SupportedHwDirective(Directive):
    def run(self):
        info = self.state.document.settings.env.config.zephyr_preview
        note = nodes.paragraph(text=(
            "In the Zephyr docs this table is generated from the board devicetree. "
            "Enabled by the board devicetree:"))
        return [note, _table(["Type", "Devicetree node", "Compatible", "Description"],
                             info["hardware"], [1, 1, 1, 3])]


class SupportedRunnersDirective(Directive):
    def run(self):
        info = self.state.document.settings.env.config.zephyr_preview
        note = nodes.paragraph(text="Runners from the board's board.cmake:")
        return [note, _table(["Runner", "Commands"], info["runners"], [1, 3])]


def code_sample_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    app = inliner.document.settings.env.app
    url = app.config.zephyr_preview["code_samples"].get(text)
    if url is None:
        return [nodes.literal(rawtext, text)], []
    return [nodes.reference(rawtext, text, refuri=url)], []


class ZephyrDomain(Domain):
    name = "zephyr"
    label = "Zephyr (preview)"
    directives = {
        "board": BoardDirective,
        "board-supported-hw": SupportedHwDirective,
        "board-supported-runners": SupportedRunnersDirective,
    }
    roles = {"code-sample": code_sample_role}

    def resolve_any_xref(self, *args, **kwargs):
        return []

    def merge_domaindata(self, docnames, otherdata):
        pass


class AppCommandsDirective(Directive):
    option_spec = {
        "zephyr-app": directives.unchanged,
        "app": directives.unchanged,
        "board": directives.unchanged,
        "goals": directives.unchanged,
    }

    def run(self):
        app = self.options.get("zephyr-app") or self.options.get("app") or "."
        board = self.options.get("board", "")
        goals = self.options.get("goals", "build").split()
        lines = [f"west build -b {board} {app}"]
        if "flash" in goals:
            lines.append("west flash")
        if "debug" in goals:
            lines.append("west debug")
        block = nodes.literal_block("\n".join(lines), "\n".join(lines))
        block["language"] = "shell"
        return [block]


def setup(app):
    app.add_config_value("hk_repo_root", "../..", "env")
    app.add_config_value("hk_github_repo", "", "env")
    app.add_config_value("hk_github_branch", "main", "env")
    app.add_config_value("hk_pages", [], "env")
    app.add_config_value("hk_board_doc", "", "env")
    app.add_config_value("zephyr_preview", {}, "env")
    app.connect("builder-inited", _generate)
    app.connect("html-page-context", _edit_link)
    app.add_domain(ZephyrDomain)
    app.add_directive("zephyr-app-commands", AppCommandsDirective)
    return {"version": "1.0", "parallel_read_safe": True, "parallel_write_safe": True}
