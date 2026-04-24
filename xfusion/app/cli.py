from __future__ import annotations

from xfusion.app.tui import XFusionTUI


def main() -> None:
    """XFusion Guardian CLI Entrypoint."""
    app = XFusionTUI()
    app.run()


if __name__ == "__main__":
    main()
