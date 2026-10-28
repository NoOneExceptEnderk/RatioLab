# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Console companion: preserve stdin/stdout exclusively for the MCP protocol."""
from ratiolab_mcp import main


if __name__ == '__main__':
    raise SystemExit(main())
