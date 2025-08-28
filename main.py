"""Modern MCP Sequential Thinking Server with enhanced architecture."""

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

# Import simplified modules
from config import check_required_api_keys
from models import ThoughtData
from session import SessionMemory
from team import create_team
from utils import setup_logging

# Initialize environment and logging
load_dotenv()
logger = setup_logging()


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Immutable server configuration."""

    provider: str
    log_level: str = "INFO"
    max_retries: int = 3
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create config from environment variables."""
        return cls(
            provider=os.environ.get("LLM_PROVIDER", "deepseek"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            max_retries=int(os.environ.get("MAX_RETRIES", "3")),
            timeout=float(os.environ.get("TIMEOUT", "30.0")),
        )


class ServerState:
    """Manages server state with proper lifecycle management."""

    def __init__(self) -> None:
        self._session: SessionMemory | None = None
        self._config: ServerConfig | None = None

    @property
    def session(self) -> SessionMemory:
        """Get current session, raising if not initialized."""
        if self._session is None:
            raise RuntimeError("Server not initialized - session unavailable")
        return self._session

    @property
    def config(self) -> ServerConfig:
        """Get current config, raising if not initialized."""
        if self._config is None:
            raise RuntimeError("Server not initialized - config unavailable")
        return self._config

    def initialize(self, config: ServerConfig, session: SessionMemory) -> None:
        """Initialize server state."""
        self._config = config
               self._session = session

    def cleanup(self) -> None:
        """Clean up server state."""
        self._session = None
        self._config = None


# Global server state
_server_state = ServerState()


class ThoughtProcessor:
    """Handles thought processing with enhanced error handling and logging."""

    __slots__ = ("_session",)

    def __init__(self, session: SessionMemory) -> None:
        self._session = session

    async def process_thought(self, thought_data: ThoughtData) -> str:
        """Process a thought through the team with comprehensive error handling."""
        try:
            return await self._process_thought_internal(thought_data)
        except Exception as e:
            logger.error(
                f"Failed to process {thought_data.thought_type.value} thought #{thought_data.thought_number}: {e}",
                exc_info=True,
            )
            raise ProcessingError(f"Thought processing failed: {e}") from e

    async def _process_thought_internal(self, thought_data: ThoughtData) -> str:
        """Internal thought processing logic."""
        logger.info(
            "Processing thought",
            extra={
                "thought_type": thought_data.thought_type.value,
                "thought_number": thought_data.thought_number,
                "total_thoughts": thought_data.total_thoughts,
                "is_revision": thought_data.is_revision,
                "branch_id": thought_data.branch_id,
            },
        )
        logger.debug(thought_data.format_for_log())

        self._session.add_thought(thought_data)

        input_prompt = self._build_input_prompt(thought_data)
        response = await self._execute_team_processing(input_prompt)

        return self._format_response(response, thought_data)

    async def _execute_team_processing(self, input_prompt: str) -> str:
        try:
            response = await self._session.team.arun(input_prompt)
            return getattr(response, "content", "") or str(response)
        except Exception as e:
            logger.warning(f"Team processing failed: {e}")
            raise ProcessingError(f"Team coordination failed: {e}") from e

    def _build_input_prompt(self, thought_data: ThoughtData) -> str:
        components = [f"Process Thought #{thought_data.thought_number}:\n"]

        match thought_data:
            case ThoughtData(is_revision=True, revises_thought=revision_num) if revision_num:
                original = self._session.find_thought_content(revision_num)
                components.append(
                    f'**REVISION of Thought #{revision_num}** (Original: "{original}")\n'
                )
            case ThoughtData(branch_from=branch_from, branch_id=branch_id) if (branch_from and branch_id):
                origin = self._session.find_thought_content(branch_from)
                components.append(
                    f'**BRANCH (ID: {branch_id}) from Thought #{branch_from}** (Origin: "{origin}")\n'
                )

        components.append(f'\nThought Content: "{thought_data.thought}"')
        return "".join(components)

    def _format_response(self, content: str, thought_data: ThoughtData) -> str:
        guidance_map = {
            True: "\n\nGuidance: Look for revision/branch recommendations in the response. Formulate the next logical thought.",
            False: "\n\nThis is the final thought. Review the synthesis.",
        }
        return content + guidance_map[thought_data.next_needed]


class ProcessingError(Exception):
    pass


@asynccontextmanager
async def app_lifespan(app) -> AsyncIterator[None]:
    config = ServerConfig.from_env()
    logger.info(
        f"Initializing Sequential Thinking Server with {config.provider} provider"
    )

    try:
        await _validate_server_requirements()

        team = create_team()
        session = SessionMemory(team=team)

        _server_state.initialize(config, session)

        logger.info("Server initialized successfully")
        yield

    except Exception as e:
        logger.error(f"Server initialization failed: {e}", exc_info=True)
        raise ServerInitializationError(f"Failed to initialize server: {e}") from e

    finally:
        logger.info("Server shutting down...")
        _server_state.cleanup()
        logger.info("Server shutdown complete")


async def _validate_server_requirements() -> None:
    missing_keys = check_required_api_keys()
    if missing_keys:
        logger.warning(f"Missing API keys: {', '.join(missing_keys)}")

    log_dir = Path.home() / ".sequential_thinking" / "logs"
    if not log_dir.exists():
        logger.info(f"Creating log directory: {log_dir}")
        log_dir.mkdir(parents=True, exist_ok=True)


class ServerInitializationError(Exception):
    pass


# Initialize FastMCP with lifespan
mcp = FastMCP(lifespan=app_lifespan)


@mcp.prompt("sequential-thinking")
def sequential_thinking_prompt(problem: str, context: str = "") -> list[dict]:
    problem = problem.strip()[:500]
    context = context.strip()[:300] if context else ""

    user_prompt = f"""Initiate sequential thinking for: {problem}
{f'Context: {context}' if context else ''}"""

    assistant_guide = f"""Starting sequential thinking process for: {problem}

Process Guidelines:
1. Estimate at least 5 total thoughts initially
2. Begin with: "Plan comprehensive analysis for: {problem}"
3. Use revisions (isRevision=True) to improve previous thoughts  
4. Use branching (branchFromThought, branchId) for alternative approaches
5. Each thought should be detailed with clear reasoning
6. Progress systematically through analysis phases

System Architecture:
- Multi-agent coordination team with specialized roles
- Planner, Researcher, Analyzer, Critic, and Synthesizer agents
- Intelligent delegation based on thought complexity
- Comprehensive synthesis of specialist responses

Ready to begin systematic analysis."""

    return [
        {
            "description": "Enhanced sequential thinking starter with comprehensive guidelines",
            "messages": [
                {"role": "user", "content": {"type": "text", "text": user_prompt}},
                {
                    "role": "assistant",
                    "content": {"type": "text", "text": assistant_guide},
                },
            ],
        }
    ]


# === NEW Pydantic Schema & Tool Definition ===

class ThoughtArgs(BaseModel):
    """Public tool input schema (camelCase) exactly as in the README."""
    thought: str
    thoughtNumber: int = Field(ge=1, description="Sequence number starting at 1")
    totalThoughts: int = Field(ge=1, description="Estimated total steps (suggest >=5)")
    nextThoughtNeeded: bool
    isRevision: bool = False
    revisesThought: int | None = None
    branchFromThought: int | None = None
    branchId: str | None = None
    needsMoreThoughts: bool = False


@mcp.tool(
    name="t1_mas_sequential_thinking",
    description="Multi-agent sequential thinking (MAS) — coordinator delegates to specialist agents and returns synthesized guidance."
)
async def t1_mas_sequential_thinking(args: ThoughtArgs) -> str:
    try:
        session = _server_state.session

        thought_data = _create_validated_thought_data(
            thought=args.thought,
            thought_number=args.thoughtNumber,
            total_thoughts=args.totalThoughts,
            next_needed=args.nextThoughtNeeded,
            is_revision=args.isRevision,
            revises_thought=args.revisesThought,
            branch_from=args.branchFromThought,
            branch_id=args.branchId,
            needs_more=args.needsMoreThoughts,
        )

        processor = ThoughtProcessor(session)
        result = await processor.process_thought(thought_data)

        logger.info(f"Successfully processed thought #{args.thoughtNumber}")
        return result

    except ValidationError as e:
        error_msg = f"Input validation failed: {e}"
        logger.error(error_msg)
        return f"Validation Error: {e}"
    except ProcessingError as e:
        error_msg = f"Processing failed: {e}"
        logger.error(error_msg)
        return f"Processing Error: {e}"
    except RuntimeError as e:
        error_msg = f"Server state error: {e}"
        logger.error(error_msg)
        return f"Server Error: {e}"
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.exception(error_msg)
        return f"Unexpected Error: {e}"


def _create_validated_thought_data(
    thought: str,
    thought_number: int,
    total_thoughts: int,
    next_needed: bool,
    is_revision: bool,
    revises_thought: int | None,
    branch_from: int | None,
    branch_id: str | None,
    needs_more: bool,
) -> ThoughtData:
    try:
        return ThoughtData(
            thought=thought.strip(),
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            next_needed=next_needed,
            is_revision=is_revision,
            revises_thought=revises_thought,
            branch_from=branch_from,
            branch_id=branch_id.strip() if branch_id else None,
            needs_more=needs_more,
        )
    except Exception as e:
        raise ValueError(f"Invalid thought data: {e}") from e


def run() -> None:
    config = ServerConfig.from_env()
    logger.info(f"Starting Sequential Thinking Server with {config.provider} provider")
    try:
        # stdio transport (proxied to HTTP/SSE by mcp-proxy in Docker CMD)
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Server stopped by user (SIGINT)")
    except SystemExit as e:
        logger.info(f"Server stopped with exit code: {e.code}")
        raise
    except Exception as e:
        logger.error(f"Critical server error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Server shutdown sequence complete")


def main() -> None:
    try:
        run()
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
