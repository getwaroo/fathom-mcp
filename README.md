# File Knowledge MCP Server

A Model Context Protocol server that provides AI assistants with direct access to local document collections through file-first search capabilities.

## Features

### Search Capabilities
- **Full-text search** with boolean operators (AND, OR, NOT) and exact phrase matching
- **Parallel search** across multiple queries for faster results
- **Fuzzy matching** and context-aware result highlighting
- **Powered by ugrep** - No database or RAG infrastructure required

### Organization
- **Hierarchical collections** - Organize knowledge using folder structures
- **Scope control** - Search globally, within collections, or in specific documents
- **Smart discovery** - Find documents by name or path patterns

### Format Support
- **PDF documents** via poppler-utils text extraction
- **Markdown files** with full formatting preservation
- **Plain text** and other common formats
- **Extensible format system** with configurable filters

### Security
- **Read-only access** - Server never modifies your documents
- **Path validation** - Prevents directory traversal attacks
- **Command sandboxing** - Filter commands run in restricted mode
- **Whitelist enforcement** - Shell filters validated before execution

## Installation

### System Dependencies

This server requires the following system utilities:

```bash
# Ubuntu/Debian
sudo apt install ugrep poppler-utils

# macOS
brew install ugrep poppler
```

### Installing via pip

```bash
pip install file-knowledge-mcp
```

## Collections and Scope

The File Knowledge server organizes documents using a **collection-based hierarchy** that maps directly to your filesystem structure.

### Understanding Collections

- A **collection** is simply a folder within your knowledge base root
- Collections can be nested to any depth
- Each document belongs to exactly one collection (its containing folder)
- The root directory itself is the top-level collection

### Configuring the Knowledge Root

The knowledge root can be specified via:

**Command-line argument** (recommended for static setups):
```bash
file-knowledge-mcp --root /path/to/documents
```

**Configuration file**:
```yaml
knowledge:
  root: "/path/to/documents"
```

**Environment variable**:
```bash
export FKM_KNOWLEDGE__ROOT=/path/to/documents
```

### Search Scopes

All search operations support three scope levels:

- **Global scope** - Search across all documents in the knowledge base
- **Collection scope** - Limit search to a specific folder and its subfolders
- **Document scope** - Search within a single document only

This hierarchical approach enables efficient knowledge organization without requiring database infrastructure.

## Configuration

### Basic Configuration

Create a `config.yaml` with your settings:

```yaml
knowledge:
  root: "./documents"

search:
  context_lines: 5        # Lines of context around matches
  max_results: 50         # Maximum results per search
  timeout: 30             # Search timeout in seconds

security:
  enable_shell_filters: true
  filter_mode: whitelist  # Recommended for production

exclude:
  patterns:
    - ".git/*"
    - "*.draft.*"
    - "*.tmp"
```

See [config.example.yaml](config.example.yaml) for all available options.

### Environment Variables

All configuration options can be overridden using environment variables with the `FKM_` prefix:

```bash
export FKM_KNOWLEDGE__ROOT=/path/to/documents
export FKM_SEARCH__MAX_RESULTS=100
export FKM_SECURITY__FILTER_MODE=whitelist
```

Use double underscores (`__`) to denote nested configuration levels.

## API

### Tools

The server implements six MCP tools organized into three categories:

#### Browse Operations
- **`list_collections`** - List folders and documents in a collection
- **`find_document`** - Find documents by name or path pattern

#### Search Operations
- **`search_documents`** - Full-text search with boolean operators
- **`search_multiple`** - Execute multiple searches in parallel

#### Read Operations
- **`read_document`** - Read document content with optional page selection
- **`get_document_info`** - Get document metadata and table of contents

### list_collections

Browse the hierarchical structure of your knowledge base.

**Arguments:**
- `path` (string, optional): Collection path relative to root. Defaults to root level.

**Returns:**
- List of subcollections (folders)
- List of documents with their paths and formats

**Example:**
```json
{
  "path": "programming/python"
}
```

### find_document

Locate documents by filename or path pattern using fuzzy matching.

**Arguments:**
- `query` (string, required): Search term for document names
- `limit` (number, optional): Maximum results to return (default: 20)

**Returns:**
- List of matching documents with paths and relevance scores

**Example:**
```json
{
  "query": "async patterns",
  "limit": 10
}
```

### search_documents

Execute full-text searches across your knowledge base with powerful boolean operators.

**Arguments:**
- `query` (string, required): Search query with optional operators
- `scope` (object, required): Defines search boundaries
  - `type` (string): One of `"global"`, `"collection"`, or `"document"`
  - `path` (string, conditional): Required for `collection` and `document` scopes

**Search Operators:**
- `term1 term2` - AND: Find documents containing both terms
- `term1|term2` - OR: Find documents containing either term
- `term1 -term2` - NOT: Exclude documents with term2
- `"exact phrase"` - Match exact phrase with quotes

**Returns:**
- List of matches with document path, line numbers, and context
- Truncation indicator if results exceed maximum

**Examples:**

Global search:
```json
{
  "query": "authentication jwt",
  "scope": {
    "type": "global"
  }
}
```

Collection-scoped search:
```json
{
  "query": "async|await -deprecated",
  "scope": {
    "type": "collection",
    "path": "programming/python"
  }
}
```

Document-specific search:
```json
{
  "query": "\"error handling\"",
  "scope": {
    "type": "document",
    "path": "guides/best-practices.md"
  }
}
```

### search_multiple

Execute multiple search queries concurrently for improved performance.

**Arguments:**
- `queries` (array of strings, required): List of search queries
- `scope` (object, required): Same scope structure as `search_documents`

**Returns:**
- Object mapping each query to its search results
- Each result includes matches and truncation status

**Example:**
```json
{
  "queries": ["authentication", "authorization", "session management"],
  "scope": {
    "type": "collection",
    "path": "security/docs"
  }
}
```

**Note:** Concurrent searches are limited by the `limits.max_concurrent_searches` configuration setting.

### read_document

Read the complete contents of a document with optional page selection for PDFs.

**Arguments:**
- `path` (string, required): Document path relative to knowledge root
- `pages` (array of numbers, optional): Specific pages to read (PDF only)

**Returns:**
- Document content as text
- Format metadata

**Examples:**

Read entire document:
```json
{
  "path": "guides/user-manual.pdf"
}
```

Read specific pages:
```json
{
  "path": "guides/user-manual.pdf",
  "pages": [1, 5, 10]
}
```

**Note:** Content length is limited by the `limits.max_read_chars` configuration setting.

### get_document_info

Retrieve metadata and structural information about a document.

**Arguments:**
- `path` (string, required): Document path relative to knowledge root

**Returns:**
- File size and format
- Page count (for PDFs)
- Table of contents with page numbers (when available)
- Last modified timestamp

**Example:**
```json
{
  "path": "reference/api-documentation.pdf"
}
```

## Usage with Claude Desktop

### Using Command-Line Arguments

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "file-knowledge": {
      "command": "file-knowledge-mcp",
      "args": ["--root", "/path/to/your/documents"]
    }
  }
}
```

### Using Configuration File

For more complex setups, use a configuration file:

```json
{
  "mcpServers": {
    "file-knowledge": {
      "command": "file-knowledge-mcp",
      "args": ["--config", "/path/to/config.yaml"]
    }
  }
}
```

### Using uv (Development)

When developing or running from source:

```json
{
  "mcpServers": {
    "file-knowledge": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/file-knowledge-mcp",
        "run",
        "file-knowledge-mcp",
        "--root",
        "/path/to/documents"
      ]
    }
  }
}
```

### Configuration File Location

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

**Important:** Restart Claude Desktop after modifying the configuration file.

## Docker Deployment

### Using docker-compose (Recommended)

```bash
# Start the server
docker-compose up

# Build and start
docker-compose up --build

# Run in detached mode
docker-compose up -d
```

The included `docker-compose.yaml` provides:
- Read-only document mounting for security
- Resource limits (512MB memory, 1 CPU)
- Proper stdio configuration for MCP protocol

### Manual Docker Build

```bash
# Build image
docker build -t file-knowledge-mcp .

# Run with read-only mount
docker run -v /path/to/docs:/knowledge:ro file-knowledge-mcp

# Run with custom configuration
docker run \
  -v /path/to/docs:/knowledge:ro \
  -v /path/to/config.yaml:/config/config.yaml:ro \
  file-knowledge-mcp
```

## Cloud Storage Integration

The File Knowledge server operates on **local documents only**. Cloud synchronization is intentionally handled outside the MCP server for security and architectural clarity.

### Recommended Approaches

**Option 1: Cloud Desktop Clients**
- Google Drive Desktop, Dropbox, OneDrive, iCloud Drive
- Automatic background sync to local folder
- Point server to synced directory

**Option 2: rclone mount**
```bash
# Mount cloud storage as read-only local directory
rclone mount gdrive:Knowledge /data/knowledge --read-only --vfs-cache-mode full --daemon
```

**Option 3: Scheduled sync**
```bash
# Periodic sync via cron
*/30 * * * * rclone sync gdrive:Knowledge /data/knowledge
```

See [`docs/cloud-sync-guide.md`](docs/cloud-sync-guide.md) for detailed setup instructions.


## Development

### Project Setup

```bash
# Clone repository
git clone https://github.com/yourusername/file-knowledge-mcp
cd file-knowledge-mcp

# Install with development dependencies (recommended)
uv sync --extra dev

# Alternative: pip
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_search.py

# Run with verbose output
uv run pytest -v
```

### Code Quality Tools

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Auto-fix linting issues
uv run ruff check . --fix

# Type checking
uv run mypy src
```

## Security

The File Knowledge server implements defense-in-depth security:

### Path Security
- **Path validation**: All file paths validated against knowledge root
- **Traversal prevention**: Blocks `../` and absolute path attacks
- **Symlink policy**: Configurable symlink following (default: disabled)

### Command Security
- **Whitelist enforcement**: Filter commands validated before execution
- **Sandboxed execution**: Shell commands run with timeout limits
- **Read-only design**: Server never modifies document collection
- **No credential access**: Server never touches cloud storage APIs

### Configuration
```yaml
security:
  enable_shell_filters: true
  filter_mode: whitelist          # Recommended for production
  allowed_filter_commands:
    - "pdftotext - -"
  symlink_policy: disallow        # Prevent symlink attacks
```

## Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging experience, I recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector file-knowledge-mcp --root /path/to/documents
```

The Inspector provides:
- Interactive tool testing
- Request/response inspection
- Server log monitoring
- Real-time debugging

You can also use the MCP Inspector to test different configurations:

```bash
npx @modelcontextprotocol/inspector file-knowledge-mcp --config config.yaml
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Run code quality checks (`ruff format`, `ruff check`, `mypy`)
5. Submit a pull request

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Resources

- [Model Context Protocol](https://modelcontextprotocol.io/) - Official MCP documentation
- [MCP Specification](https://spec.modelcontextprotocol.io/) - Protocol specification
- [ugrep](https://github.com/Genivia/ugrep) - Ultra-fast grep with boolean search
- [poppler-utils](https://poppler.freedesktop.org/) - PDF rendering utilities
