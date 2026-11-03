Zephyr on the M2S Hello FPGA Kit
################################

Zephyr RTOS firmware for the Microchip **M2S Hello FPGA Kit** (SmartFusion2 M2S010-VF256), a
Python test GUI for the board, and a reworked Zephyr board documentation for the kit.

.. image:: https://github.com/codespaces/badge.svg
   :target: https://codespaces.new/bavariamatic-GmbH/Zephyr-M2S-Hello-FPGA-Kit
   :alt: Open in GitHub Codespaces

What is in the project
**********************

- **Firmware** (``src/``): I2C demo with an LTR-329ALS light sensor, raw SPI transfers, the SPI
  flash U8 (SST26VF064B), the debug LEDs LD1–LD3 and the ``hk`` shell commands. See
  :doc:`generated/project`.
- **Test GUI** (``tools/hello_fpga_gui``): console, LEDs, raw I2C/SPI for a logic analyzer, SPI
  flash read/write/erase, debug log. See :doc:`generated/gui`.
- **Libero design contract** for the M2S010-VF256: MSS clocks and the pins of every peripheral.
  See :doc:`generated/libero`.
- **Zephyr board documentation** proposed for upstream Zephyr: how the kit is really programmed
  (Hello FPGA GUI), the console path through the PIC32 and the issues found on the board. See
  :doc:`generated/zephyr-board/index`.

.. graphviz::
   :caption: How the parts fit together

   digraph overview {
      rankdir=LR;
      node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];
      edge [fontname="Helvetica", fontsize=10];

      repo   [label="This repository\nZephyr application\n(west build)"];
      libero [label="Libero SoC\nMSS design + eNVM client\nzephyr.hex"];
      dat    [label="DAT file"];
      hgui   [label="Microchip\nHello FPGA GUI"];
      kit    [label="M2S Hello FPGA Kit\nSmartFusion2 M2S010"];
      tgui   [label="Test GUI\ntools/hello_fpga_gui"];

      repo -> libero [label="zephyr.hex"];
      libero -> dat [label="Export Bitstream"];
      dat -> hgui -> kit [label="program"];
      tgui -> kit [label="USB serial, hk shell", dir=both];
   }

Build environment
*****************

The firmware builds in a container with the Zephyr SDK (ARM toolchain only), west and CMake. The
image is published to the GitHub Container Registry and used by the dev container:

.. code-block:: text

   ghcr.io/bavariamatic-gmbh/zephyr-m2s-hello-fpga-kit

- **GitHub Codespaces:** open the repository in a codespace (button above). The workspace is
  initialised on creation (``west init`` / ``west update``); build with
  ``west build -b m2s_hello_fpga_kit/m2s010 -d build`` or the VS Code task *Zephyr: Build*.
- **VS Code on your computer:** *Dev Containers: Reopen in Container* uses the same image.

Libero SoC and the Hello FPGA GUI are Windows/Linux desktop tools and are not part of the
container.

.. toctree::
   :caption: Project
   :maxdepth: 2

   generated/project
   generated/gui

.. toctree::
   :caption: Hardware
   :maxdepth: 2

   generated/libero
   generated/jlink

.. toctree::
   :caption: Zephyr board documentation
   :maxdepth: 2

   generated/zephyr-board/index
   generated/zephyr-pr
