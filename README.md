# JLCPCB MCP Server

MCP server for searching JLCPCB electronic components directly from Claude, Cursor, and other AI coding assistants. Search 1.5M+ parts for PCB assembly with real-time stock and pricing.

**Website:** [jlcmcp.dev](https://jlcmcp.dev)

## Features

- Search 1.5M+ JLCPCB components by keyword, category, stock, package, manufacturer
- Filter by library type (basic/preferred = no fee, extended = $3 fee)
- Get detailed part info including pricing tiers and datasheets
- Browse 52 component categories and subcategories
- Real-time stock levels from JLCPCB
- No API key or authentication required

## Quick Start

### Claude Code

```bash
claude mcp add --transport http jlcmcp https://jlcmcp.dev/mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jlcmcp": {
      "type": "http",
      "url": "https://jlcmcp.dev/mcp"
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "jlcmcp": {
      "type": "http",
      "url": "https://jlcmcp.dev/mcp"
    }
  }
}
```

### VSCode

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "jlcmcp": {
      "type": "http",
      "url": "https://jlcmcp.dev/mcp"
    }
  }
}
```

### Other MCP Clients (stdio via mcp-remote)

```json
{
  "mcpServers": {
    "jlcmcp": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://jlcmcp.dev/mcp"]
    }
  }
}
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `search_parts` | Search JLCPCB components by keyword, category, stock, package, manufacturer |
| `get_part` | Get full details for a specific LCSC part code |
| `list_categories` | Get all 52 primary component categories |
| `get_subcategories` | Get subcategories for a category |
| `get_version` | Server version and health status |

## Example Prompts

```
"Search for 0402 100nF capacitors with at least 1000 in stock"
"Find ESP32 modules in the basic library" (no assembly fee)
"Get details for part C82899"
"List all JLCPCB component categories"
"Search for STM32 microcontrollers"
"Find USB-C connectors with stock over 5000"
```

## JLCPCB Library Types

JLCPCB has three library types that affect PCB assembly fees:

| Type | Fee | Description |
|------|-----|-------------|
| `basic` | None | Common parts in JLCPCB's standard library |
| `preferred` | None | Recommended parts with good availability |
| `extended` | $3/unique | Less common parts |

Use `library_type="no_fee"` to search both basic and preferred parts combined.

## API Details

- **Endpoint:** `https://jlcmcp.dev/mcp`
- **Transport:** Streamable HTTP (MCP 2.0+)
- **Health:** `https://jlcmcp.dev/health`
- **Rate Limit:** 100 requests/minute per IP
- **Authentication:** None required

## Self-Hosting

### Running Locally

```bash
# Clone and setup
git clone https://github.com/Averyy/jlcpcb-mcp
cd jlcpcb-mcp
uv venv && uv pip install -e ".[dev]"

# Run server
.venv/bin/python -m jlcpcb_mcp.server
```

Server runs at `http://localhost:8080/mcp`

### Docker Deployment

```bash
docker compose up -d
```

## Running Tests

```bash
# All tests (unit + integration)
.venv/bin/pytest tests/ -v

# Unit tests only
.venv/bin/pytest tests/ -v -k "not Integration"
```

## License

MIT

## Links

- **Website:** [jlcmcp.dev](https://jlcmcp.dev)
- **JLCPCB Parts Library:** [jlcpcb.com/parts](https://jlcpcb.com/parts)
- **MCP Protocol:** [modelcontextprotocol.io](https://modelcontextprotocol.io)
