# file-knowledge-mcp

File-first knowledge base MCP server. Search and read documents (PDF, Markdown, text) through Claude Desktop.

## Features

- **File-first approach**: Search directly in files using ugrep (no database/RAG required)
- **Browse**: List collections and find documents by name
- **Search**: Full-text search with boolean operators (AND, OR, NOT)
- **Read**: Read document content with page selection for PDFs
- **Formats**: PDF, Markdown, Text (extensible via config)
- **Security-first**: Path validation, command sandboxing, read-only by design

## Prerequisites

- Python 3.12+
- [ugrep](https://github.com/Genivia/ugrep) (`brew install ugrep` or `apt install ugrep`)
- [poppler-utils](https://poppler.freedesktop.org/) for PDF (`brew install poppler` or `apt install poppler-utils`)

## Quick Start

### 1. Install

```bash
# Clone or download this repository
cd file-knowledge-mcp

# Install with uv (recommended)
uv sync --extra dev

# Or with pip
pip install -e ".[dev]"
```

### 2. Configure

Copy the example config:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` and set your documents path:

```yaml
knowledge:
  root: "/path/to/your/documents"
```

Or skip the config file and use CLI:

```bash
uv run file-knowledge-mcp --root /path/to/docs
```

### 3. Test Locally

```bash
# Run tests
uv run pytest

# Start server (test mode)
uv run file-knowledge-mcp --root ./documents
```

### 4. Connect to Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "file-knowledge": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/file-knowledge-mcp",
        "run",
        "file-knowledge-mcp",
        "--root",
        "/path/to/your/documents"
      ]
    }
  }
}
```

Or with config file:

```json
{
  "mcpServers": {
    "file-knowledge": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/file-knowledge-mcp",
        "run",
        "file-knowledge-mcp",
        "--config",
        "/path/to/config.yaml"
      ]
    }
  }
}
```

Restart Claude Desktop.

## Usage

Once connected, you can ask Claude:

- "What documents do I have about Python?"
- "Search for 'async patterns' in my programming notes"
- "Read the Introduction section from tutorial.pdf"
- "Find all mentions of 'authentication' in the docs folder"

## Tools

### list_collections

Browse folders in your knowledge base.

```json
{
  "path": "programming/python"
}
```

### find_document

Find documents by name.

```json
{
  "query": "async",
  "limit": 10
}
```

### search_documents

Full-text search with boolean operators.

```json
{
  "query": "authentication jwt",
  "scope": {
    "type": "global"
  }
}
```

Query syntax:
- `term1 term2` - AND (both terms)
- `term1|term2` - OR (either term)
- `term1 -term2` - NOT (exclude term2)
- `"exact phrase"` - Exact match

### read_document

Read document content.

```json
{
  "path": "guides/tutorial.pdf",
  "pages": [1, 2, 3]
}
```

## Configuration

See `config.example.yaml` for all options.

Key settings:
- `knowledge.root`: Path to documents (required)
- `formats`: File type configurations and filters
- `search.context_lines`: Context around matches (default: 5)
- `exclude.patterns`: Files to ignore

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov

# Format code
uv run ruff format .

# Lint
uv run ruff check .
```

## Project Structure

```
file-knowledge-mcp/
├── src/file_knowledge_mcp/
│   ├── config.py          # Configuration management
│   ├── errors.py          # Error definitions
│   ├── security.py        # Security controls
│   ├── server.py          # MCP server
│   ├── __main__.py        # CLI entry point
│   ├── tools/
│   │   ├── browse.py      # list_collections, find_document
│   │   ├── search.py      # search_documents
│   │   └── read.py        # read_document
│   └── search/
│       └── ugrep.py       # Search engine wrapper
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_browse.py
│   └── test_read.py
└── docs/
    └── cloud-sync-guide.md  # Cloud storage integration
```

## Cloud Storage Integration

This MCP server provides **read-only** access to your local knowledge base. Cloud synchronization is intentionally kept **outside** the server for security and architectural reasons.

If you need to sync documents from cloud storage (Google Drive, Dropbox, OneDrive, S3, etc.), see our comprehensive guide:

**📖 [Cloud Storage Integration Guide](docs/cloud-sync-guide.md)**

The guide covers three recommended approaches:
- **rclone mount** - Mount cloud storage as local filesystem (recommended for production)
- **Cloud Desktop Clients** - Use official sync clients (easiest for desktop)
- **Scheduled Sync** - Periodic sync with cron/systemd (most efficient for servers)

All approaches maintain proper security boundaries by keeping sync operations separate from the MCP server.

## License

MIT
