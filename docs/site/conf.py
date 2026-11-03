# Sphinx configuration of the project web page (GitHub Pages).
#
# Build:   sphinx-build -W --keep-going -b html docs/site docs/site/_build/html
# Preview: VS Code task "Docs: Live preview" (docker compose service "docs").
#
# The pages under generated/ are copied from the repository by _ext/hk_site.py
# on every build; edit the originals (README.md, docs/*.md, ...), not the copies.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_ext"))

project = "Zephyr on the M2S Hello FPGA Kit"
author = "Bavariamatic GmbH"
copyright = "Bavariamatic GmbH"

extensions = [
    "myst_parser",
    "sphinx.ext.graphviz",
    "sphinx_copybutton",
    "hk_site",
]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build", "_ext", "Dockerfile", "requirements.txt"]

# GitHub-style heading anchors, so links like README.md#console-connection work
myst_heading_anchors = 4
myst_enable_extensions = ["colon_fence"]
# Copied README files contain links to source files that become GitHub URLs
suppress_warnings = ["myst.header"]

graphviz_output_format = "svg"

html_theme = "sphinx_rtd_theme"
html_title = project
html_static_path = ["_static"]
html_css_files = ["hk.css"]
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
}
html_context = {
    "display_github": True,
    "github_user": "bavariamatic-GmbH",
    "github_repo": "Zephyr-M2S-Hello-FPGA-Kit",
    "github_version": "main",
    "conf_py_path": "/docs/site/",
}

# ---------------------------------------------------------------- hk_site extension

hk_repo_root = "../.."
hk_github_repo = "bavariamatic-GmbH/Zephyr-M2S-Hello-FPGA-Kit"
hk_github_branch = "main"

# (file in the repository, page under generated/)
hk_pages = [
    ("README.md", "project.md"),
    ("tools/hello_fpga_gui/README.md", "gui.md"),
    ("docs/libero-hello-fpga-vf256.md", "libero.md"),
    ("docs/jlink-debug.md", "jlink.md"),
    ("docs/zephyr-upstream/README.md", "zephyr-pr.md"),
]
hk_board_doc = "docs/zephyr-upstream/boards/microchip/m2s_hello_fpga_kit/doc"

# Values the Zephyr directives would read from the board files
# (boards/microchip/m2s_hello_fpga_kit in Zephyr v4.5.0-rc3)
zephyr_preview = {
    "full_name": "Microchip M2S Hello FPGA Kit",
    "target": "m2s_hello_fpga_kit/m2s010",
    "vendor": "Microchip Technology Inc.",
    "arch": "arm",
    "soc": "m2s010 (SmartFusion2)",
    "hardware": [
        ("Serial", "uart0", "ns16550", "MMUART_0, console and shell (via the PIC32)"),
        ("GPIO", "gpio0", "microchip,mpfs-gpio", "MSS GPIO, LD1 as led0"),
    ],
    "runners": [
        ("openocd", "flash, debug, attach, rtt, debugserver (not usable on an unmodified kit)"),
    ],
    "code_samples": {
        "hello_world": "https://docs.zephyrproject.org/latest/samples/hello_world/README.html",
        "blinky": "https://docs.zephyrproject.org/latest/samples/basic/blinky/README.html",
    },
}
