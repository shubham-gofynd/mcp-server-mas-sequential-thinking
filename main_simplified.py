"""Simplified MCP Sequential Thinking Server using modular architecture."""

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError
from dotenv import load_dotenv

# Import simplified modules
from config import check_required_api_keys
from models import ThoughtData
from session import SessionMemory
from team import create_team
from utils import setup_logging

load_dotenv()
logger = setup_logging()

# Global session context
session: Optional[SessionMemory] = None


class ThoughtProcessor:
    """Handles thought processing with simplified logic."""
    
    def __init__(self, session: SessionMemory):
        self.session = session
    
    async def process_thought(self, thought_data: ThoughtData) -> str:
        """Process a thought through the team and return response."""
        # Log the thought
        logger.info(f"Processing {thought_data.thought_type.value} thought #{thought_data.thought_number}")
        logger.debug(thought_data.format_for_log())
        
        # Add to session
        self.session.add_thought(thought_data)
        
        # Prepare input with context
        input_prompt = self._build_input_prompt(thought_data)
        
        # Process through team
        response = await self.session.team.arun(input_prompt)
        
        # Extract content
        content = getattr(response, 'content', '') or str(response)
        
        # Add guidance
        if thought_data.next_needed:
            content += "\n\nGuidance: Look for revision/branch recommendations in the response. Formulate the next logical thought."
        else:
            content += "\n\nThis is the final thought. Review the synthesis."
        
        return content
    
    def _build_input_prompt(self, thought_data: ThoughtData) -> str:
        """Build input prompt with appropriate context."""
        prompt = f"Process Thought #{thought_data.thought_number}:\\n"
        
        # Add context for revisions/branches
        if thought_data.is_revision and thought_data.revises_thought:
            original = self.session.find_thought_content(thought_data.revises_thought)
            prompt += f"**REVISION of Thought #{thought_data.revises_thought}** (Original: \"{original}\")\\n"
        elif thought_data.branch_from and thought_data.branch_id:
            origin = self.session.find_thought_content(thought_data.branch_from)
            prompt += f"**BRANCH (ID: {thought_data.branch_id}) from Thought #{thought_data.branch_from}** (Origin: \"{origin}\")\\n"
        
        prompt += f"\\nThought Content: \"{thought_data.thought}\""
        return prompt


@asynccontextmanager
async def app_lifespan() -> AsyncIterator[None]:
    """Manage application lifecycle."""
    global session
    logger.info("Initializing Sequential Thinking Server...")
    
    try:
        # Check required API keys
        missing_keys = check_required_api_keys()
        if missing_keys:
            logger.warning(f"Missing API keys: {missing_keys}")
        
        # Create team and session
        team = create_team()
        session = SessionMemory(team=team)
        logger.info("Server initialized successfully")
        
        yield
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        session = None


# Initialize FastMCP with lifespan
mcp = FastMCP(lifespan=app_lifespan)


@mcp.prompt("sequential-thinking")
def sequential_thinking_prompt(problem: str, context: str = ""):
    """Starter prompt for sequential thinking."""
    user_prompt = f"""Initiate sequential thinking for: {problem}
{f'Context: {context}' if context else ''}"""

    assistant_guide = f"""Starting sequential thinking process.

Guidelines:
1. Estimate at least 5 total thoughts initially
2. First thought: "Plan comprehensive analysis for: {problem}"
3. Use revisions (isRevision=True) to improve previous thoughts
4. Use branching (branchFromThought, branchId) for alternatives
5. Each thought should be detailed and explain reasoning

The system uses a coordinate-mode team that will analyze, delegate, and synthesize responses."""

    return [{
        "description": "Sequential thinking starter with problem and guidelines",
        "messages": [
            {"role": "user", "content": {"type": "text", "text": user_prompt}},
            {"role": "assistant", "content": {"type": "text", "text": assistant_guide}}
        ]
    }]


@mcp.tool()
async def sequentialthinking(
    thought: str,
    thought_number: int, 
    total_thoughts: int,
    next_needed: bool,
    is_revision: bool = False,
    revises_thought: Optional[int] = None,
    branch_from: Optional[int] = None,
    branch_id: Optional[str] = None,
    needs_more: bool = False
) -> str:
    """
    Sequential thinking tool for complex problem-solving.
    
    Processes thoughts through a multi-agent team that coordinates specialists
    to analyze, plan, research, critique, and synthesize responses.
    
    Args:
        thought: Content of the thinking step
        thought_number: Sequence number (≥1)  
        total_thoughts: Estimated total thoughts (≥5)
        next_needed: Whether another thought follows
        is_revision: Whether this revises a previous thought
        revises_thought: Thought number being revised
        branch_from: Thought number to branch from
        branch_id: Unique branch identifier
        needs_more: Whether more thoughts needed beyond estimate
    
    Returns:
        Team's synthesized response with guidance for next steps
    """
    global session
    
    if not session:
        return "Error: Session not initialized"
    
    try:
        # Create and validate thought data
        thought_data = ThoughtData(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            next_needed=next_needed,
            is_revision=is_revision,
            revises_thought=revises_thought,
            branch_from=branch_from,
            branch_id=branch_id,
            needs_more=needs_more
        )
        
        # Process through team
        processor = ThoughtProcessor(session)
        return await processor.process_thought(thought_data)
        
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        return f"Input validation failed: {e}"
    except Exception as e:
        logger.exception("Error processing thought")
        return f"Processing error: {e}"


def run():
    """Run the MCP server."""
    provider = os.environ.get("LLM_PROVIDER", "deepseek")
    logger.info(f"Starting Sequential Thinking Server with {provider}")
    
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()