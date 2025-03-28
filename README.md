# mcp-llms

Minimal example of MCP for parsing `llms.txt`

## Installation

```bash
uv pip install -e .
```

## Usage With Claude Desktop

Add the following to your `claude_desktop_config.json` file (mine is located in `/Users/hamel/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    ... // other mcp servers
    "llms-txt-parser": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/hamel/git/mcp-llms.txt/mcp_llms", // Path to the mcp_llms directory
        "run",
        "llms_txt.py"
      ],
      "env": {
        "ANTHROPIC_API_KEY": "<Your Anthropic API Key>"
      }
    }
  }
}
```
