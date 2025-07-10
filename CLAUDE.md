# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Dependencies & Environment
- Use `uv` for dependency management (preferred over pip)
- Install dependencies: `uv pip install -e .` or `uv pip install -r requirements.txt`
- Install dev dependencies: `uv pip install -e ".[dev]"`
- Upgrade agno: `uv pip install --upgrade agno`
- Test Python imports: `uv run python -c "import agno; print('Agno imported successfully')"`

### Code Quality
- Linting: `ruff check . --fix`
- Formatting: `black .`
- Type checking: `mypy .`
- Testing: `pytest`

### Running the Server
- Direct execution: `uv run python main.py`
- Using uv: `uv run mcp-server-mas-sequential-thinking`
- Package execution: `uvx mcp-server-mas-sequential-thinking`

## Project Architecture

This is a Multi-Agent System (MAS) for sequential thinking built with the Agno framework and served via MCP.

### Core Components

**Main Entry Point:** `main.py` contains all core logic:
- FastMCP server setup
- ThoughtData Pydantic model for input validation
- Multi-agent team creation and coordination
- Sequential thinking tool implementation

**Agent Architecture:**
- **Team Coordinator:** Uses Agno's `Team` object in `coordinate` mode
- **Specialist Agents:** Planner, Researcher, Analyzer, Critic, Synthesizer
- **Agent Flow:** Coordinator receives thoughts → delegates to specialists → synthesizes responses

### Key Functions

**`create_sequential_thinking_team()`:** Instantiates the multi-agent team with specialized roles
**`sequentialthinking` tool:** Core MCP tool that processes ThoughtData objects
**`get_model_config()`:** Configures LLM providers (DeepSeek, Groq, OpenRouter)

### Configuration

Environment variables control behavior:
- `LLM_PROVIDER`: Provider selection (deepseek, groq, openrouter)
- `{PROVIDER}_API_KEY`: API keys for each provider
- `{PROVIDER}_{TEAM|AGENT}_MODEL_ID`: Model selection for coordinator vs specialists
- `EXA_API_KEY`: For research capabilities

### Data Flow

1. External LLM calls `sequentialthinking` tool with ThoughtData
2. Tool validates input via Pydantic model
3. Coordinator analyzes thought and delegates to relevant specialists
4. Specialists process sub-tasks using their tools (ThinkingTools, ExaTools)
5. Coordinator synthesizes responses and returns guidance
6. Process continues with revisions/branches as needed

### Memory & State

- **SessionMemory:** In-memory storage for thought history and branches
- **Logging:** Structured logging to `~/.sequential_thinking/logs/`
- **Branch Management:** Supports non-linear thinking with branch tracking

## Important Notes

- This is a high-token-usage system due to multi-agent architecture
- All agent definitions are contained in `main.py`
- The system supports revisions and branching for complex problem-solving
- Configuration is entirely environment-based (no config files)