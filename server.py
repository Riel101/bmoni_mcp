"""Entry point for the BMONI MCP server.

Examples
--------
Export BMONI_BASE_URL and BMONI_API_KEY first (see .env.example).

stdio (default - connect a desktop MCP client / agent to this command):
    python server.py

Streamable HTTP / SSE on a port:
    python server.py --transport http --host 0.0.0.0 --port 8000

List every registered tool and exit:
    python server.py --list-tools
"""

from bmoni_mcp.cli import main

if __name__ == "__main__":
    main()
