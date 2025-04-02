import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from agno.team.team import Team
from agno.tools.exa import ExaTools
from dotenv import load_dotenv
from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)

# Add logging imports and setup
import logging
import logging.handlers
from pathlib import Path

# Configure logging system
def setup_logging() -> logging.Logger:
    """
    Setup application logging with both file and console handlers.
    Logs will be stored in user's home directory under .sequential_thinking/logs
    
    Returns:
        Logger instance configured with both handlers
    """
    # Create logs directory in user's home
    home_dir = Path.home()
    log_dir = home_dir / ".sequential_thinking" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("sequential_thinking")
    logger.setLevel(logging.DEBUG)
    
    # Log format
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "sequential_thinking.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# Load environment variables from .env file
load_dotenv()

# --- Pydantic Model for Tool Input Schema ---

class ThoughtData(BaseModel):
    """
    Represents the data structure for a single thought in the sequential
    thinking process. This model is used as the input schema for the
    'sequentialthinking' tool. The clarity and specificity of the 'thought'
    field is crucial for internal routing.
    """
    thought: str = Field(
        ...,
        description="The content of the current thought or step. Make it specific enough to imply the desired action (e.g., 'Analyze X', 'Critique Y', 'Plan Z', 'Research A').",
        min_length=1
    )
    thoughtNumber: int = Field(
        ...,
        description="The sequence number of this thought.",
        ge=1
    )
    totalThoughts: int = Field(
        ...,
        description="The estimated total number of thoughts required.",
        ge=1
    )
    nextThoughtNeeded: bool = Field(
        ...,
        description="Indicates if another thought step is needed after this one."
    )
    isRevision: bool = Field(
        False,
        description="Indicates if this thought revises a previous thought."
    )
    revisesThought: Optional[int] = Field(
        None,
        description="The number of the thought being revised, if isRevision is True.",
        ge=1
    )
    branchFromThought: Optional[int] = Field(
        None,
        description="The thought number from which this thought branches.",
        ge=1
    )
    branchId: Optional[str] = Field(
        None,
        description="An identifier for the branch, if branching."
    )
    needsMoreThoughts: bool = Field(
        False,
        description="Indicates if more thoughts are needed beyond the current estimate."
    )

    # Pydantic model configuration
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        frozen=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "examples": [
                {
                    "thought": "Analyze the core assumptions of the previous step.",
                    "thoughtNumber": 2,
                    "totalThoughts": 5,
                    "nextThoughtNeeded": True,
                    "isRevision": False,
                    "revisesThought": None,
                    "branchFromThought": None,
                    "branchId": None,
                    "needsMoreThoughts": False
                },
                {
                    "thought": "Critique the proposed solution for potential biases.",
                    "thoughtNumber": 4,
                    "totalThoughts": 5,
                    "nextThoughtNeeded": True,
                    "isRevision": False,
                    "revisesThought": None,
                    "branchFromThought": None,
                    "branchId": None,
                    "needsMoreThoughts": False
                }
            ]
        }
    )

    # --- Validators ---

    @field_validator('revisesThought')
    @classmethod
    def validate_revises_thought(cls, v: Optional[int], values: Dict[str, Any]) -> Optional[int]:
        is_revision = values.data.get('isRevision', False)
        if v is not None and not is_revision:
            raise ValueError('revisesThought can only be set when isRevision is True')
        return v

    @field_validator('branchId')
    @classmethod
    def validate_branch_id(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        branch_from_thought = values.data.get('branchFromThought')
        if v is not None and branch_from_thought is None:
            raise ValueError('branchId can only be set when branchFromThought is set')
        return v

    @model_validator(mode='after')
    def validate_thought_numbers(self) -> 'ThoughtData':
        if self.thoughtNumber > self.totalThoughts:
             pass # Allow potential adjustment downstream
        if self.revisesThought is not None and self.revisesThought >= self.thoughtNumber:
            raise ValueError('revisesThought must be less than thoughtNumber')
        if self.branchFromThought is not None and self.branchFromThought >= self.thoughtNumber:
            raise ValueError('branchFromThought must be less than thoughtNumber')
        return self

# --- Utility for Formatting Thoughts (for Logging) ---

def format_thought_for_log(thought_data: ThoughtData) -> str:
    """Formats a thought for logging purposes."""
    prefix = ''
    context = ''

    if thought_data.isRevision:
        prefix = '🔄 Revision'
        context = f' (revising thought {thought_data.revisesThought})'
    elif thought_data.branchFromThought:
        prefix = '🌿 Branch'
        context = f' (from thought {thought_data.branchFromThought}, ID: {thought_data.branchId})'
    else:
        prefix = '💭 Thought'
        context = ''

    header = f"{prefix} {thought_data.thoughtNumber}/{thought_data.totalThoughts}{context}"
    border_len = max(len(header.encode('utf-8', 'ignore')), len(thought_data.thought.encode('utf-8', 'ignore'))) + 4
    border = '─' * border_len

    thought_lines = []
    current_line = ""
    for word in thought_data.thought.split():
        test_line = current_line + (" " if current_line else "") + word
        if len(test_line.encode('utf-8', 'ignore')) <= border_len - 4: # Account for '│ ' and ' │'
            current_line = test_line
        else:
            thought_lines.append(current_line)
            current_line = word
    thought_lines.append(current_line)

    formatted_thought_lines = [f"│ {line:<{border_len - 4}} │" for line in thought_lines] # Use ljust with correct width

    return f"""
┌{'─' * (border_len - 2)}┐
│ {header:<{border_len - 4}} │
├{'─' * (border_len - 2)}┤
{''.join(formatted_thought_lines)}
└{'─' * (border_len - 2)}┘"""


# --- Agno Multi-Agent Team Setup ---

def create_sequential_thinking_team() -> Team:
    """
    Creates and configures the Agno multi-agent team for sequential thinking,
    using the 'coordinate' mode with a dedicated coordinator.

    Returns:
        An initialized Team instance.
    """
    try:
        # Use a capable model for all agents
        model = DeepSeek(id="deepseek-chat")
    except Exception as e:
        logger.error(f"Error initializing base model: {e}")
        logger.error("Please ensure the necessary API keys and configurations are set.")
        sys.exit(1)

    # Create the coordinator agent
    coordinator = Agent(
        name="Coordinator",
        role="Team Coordinator",
        description="Coordinates the team's efforts by breaking down tasks and synthesizing results.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Team Coordinator responsible for orchestrating the sequential thinking process.",
            "Your core responsibilities:",
            " 1. Analyze incoming tasks and break them into appropriate subtasks",
            " 2. Identify which team members are best suited for each subtask",
            " 3. Coordinate parallel work streams when possible",
            " 4. Synthesize team members' outputs into coherent responses",
            " 5. Maintain overall quality and consistency",
            " 6. Track progress and adjust the plan as needed",
            "For each thought processing task:",
            " - First carefully analyze the thought content and context",
            " - Break it down into specialized subtasks aligned with team members' expertise",
            " - ALWAYS delegate subtasks to specific team members by name",
            " - Consider which combination of experts is needed for each thought",
            " - Provide clear instructions and context to each team member",
            " - After receiving team members' outputs, synthesize them into a coherent response",
            " - Structure the final response to clearly show logical progression",
            " - Ensure all aspects of the thought have been thoroughly addressed",
        ],
        model=model
    )

    # Agent definitions for team members
    planner = Agent(
        name="Planner",
        role="Strategic Planner",
        description="Develops strategic plans and evaluates steps.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are responsible for strategic planning and evaluation.",
            "When assigned a task by the coordinator:",
            " - Break down complex problems into manageable steps",
            " - Evaluate strategic fit of current steps",
            " - Suggest adjustments to the overall plan",
            " - Consider timeline and resource implications",
            "Provide clear, actionable planning insights or evaluations.",
        ],
        model=model
    )

    researcher = Agent(
        name="Researcher",
        role="Information Gatherer",
        description="Gathers and validates information.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are responsible for gathering and analyzing information.",
            "When assigned a task by the coordinator:",
            " - Assess information needs for the task",
            " - Gather relevant external data using search tools",
            " - Validate and verify information sources",
            " - Synthesize findings into actionable insights",
            "Return clear, well-organized research findings.",
        ],
        tools=[ExaTools()],
        model=model
    )

    analyzer = Agent(
        name="Analyzer",
        role="Core Analyst",
        description="Performs deep analysis and generates insights.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are responsible for core analysis and insight generation.",
            "When assigned a task by the coordinator:",
            " - Break down complex concepts",
            " - Identify key patterns and relationships",
            " - Generate insights and implications",
            " - Structure findings logically",
            "Provide clear, structured analysis results.",
        ],
        model=model
    )

    critic = Agent(
        name="Critic",
        role="Quality Controller",
        description="Evaluates quality and suggests improvements.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are responsible for evaluation and quality improvement.",
            "When assigned a task by the coordinator:",
            " - Evaluate logical consistency",
            " - Identify potential biases or gaps",
            " - Suggest specific improvements",
            " - Provide constructive feedback",
            "Return clear, actionable critique and suggestions.",
        ],
        model=model
    )

    synthesizer = Agent(
        name="Synthesizer",
        role="Integration Specialist",
        description="Integrates information and forms conclusions.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are responsible for integration and synthesis.",
            "When assigned a task by the coordinator:",
            " - Combine insights from multiple sources",
            " - Identify key themes and patterns",
            " - Form coherent conclusions",
            " - Structure information clearly",
            "Provide clear, integrated summaries and conclusions.",
        ],
        model=model
    )

    # Create the team with the coordinator as leader
    team = Team(
        name="SequentialThinkingTeam",
        mode="coordinate",
        members=[planner, researcher, analyzer, critic, synthesizer],
        description="A coordinated multi-agent team for sequential thinking and problem analysis.",
        success_criteria=[
            "Break down complex problems effectively",
            "Utilize team members' specialized skills appropriately",
            "Maintain high quality and consistency across outputs",
            "Produce well-reasoned, comprehensive responses",
            "Demonstrate clear logical progression in analysis"
        ],
        markdown=True,
        debug_mode=True
    )

    return team

# --- Application Context and Lifespan Management ---

@dataclass
class AppContext:
    """Holds shared application resources, like the Agno team."""
    team: Team

app_context: Optional[AppContext] = None

@asynccontextmanager
async def app_lifespan() -> AsyncIterator[None]:
    """Manages the application lifecycle."""
    global app_context
    logger.info("Initializing application resources (Coordinate Mode)...")
    team = create_sequential_thinking_team()
    app_context = AppContext(team=team)
    logger.info("Agno team initialized in coordinate mode.")
    try:
        yield
    finally:
        logger.info("Shutting down application resources...")
        app_context = None

# Initialize FastMCP
mcp = FastMCP()

# --- MCP Handlers ---

@mcp.prompt("sequential-thinking-starter")
def sequential_thinking_starter(problem: str, context: str = ""):
    """Starter prompt for sequential thinking with enhanced multi-step process."""
    prompt_text = f"""Initiate a comprehensive sequential thinking process for the following problem:

Problem: {problem}
{f'Context: {context}' if context else ''}

Instructions for your sequential thinking process:
1. Analyze the problem complexity to determine an appropriate number of thinking steps (minimum 5 steps for proper analysis)

2. For your first step, call the 'sequentialthinking' tool with:
   - thoughtNumber: 1
   - totalThoughts: (your estimated number of steps, at least 5)
   - nextThoughtNeeded: True
   
3. Structure your first thought to engage multiple team members:
   "Plan a comprehensive analysis approach for: {problem}
   Objectives for team members:
   - Strategic Planner: [specific planning task]
   - Researcher: [specific research questions]
   - Analyzer: [specific analysis focus]
   - Critic: [specific evaluation criteria]
   - Synthesizer: [specific integration goal]"

4. In subsequent steps, consider using these features to enhance analysis:
   - isRevision: True (with revisesThought) for deepening analysis of earlier steps
   - branchFromThought (with branchId) for exploring alternative perspectives
   - needsMoreThoughts: True if complexity requires additional steps beyond initial estimate

5. Each thought should:
   - Clearly specify which team members to engage
   - Define concrete objectives for each team member
   - Include context from previous steps
   - Outline expected outputs"""

    return {
        "description": "Flexible starter prompt for sequential thinking (coordinate mode)",
        "messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]
    }

@mcp.tool()
def sequentialthinking(thought: str, thoughtNumber: int, totalThoughts: int, nextThoughtNeeded: bool,
                      isRevision: bool = False, revisesThought: Optional[int] = None,
                      branchFromThought: Optional[int] = None, branchId: Optional[str] = None,
                      needsMoreThoughts: bool = False) -> str:
    """
    Processes one step in a sequential thinking chain through coordinated multi-agent analysis.
    
    This tool orchestrates a team of specialized agents to break down and analyze complex problems:
    - Team Coordinator: Decomposes tasks and coordinates team efforts
    - Strategic Planner: Develops strategic approaches and evaluates steps
    - Information Gatherer: Researches and validates information
    - Core Analyst: Performs deep analysis and generates insights
    - Quality Controller: Evaluates and suggests improvements
    - Integration Specialist: Synthesizes information and forms conclusions

    Each thought typically goes through multiple phases:
    1. Task Decomposition (Coordinator)
       - Breaking down the thought into subtasks
       - Identifying required expertise
       - Planning parallel processing opportunities

    2. Multi-Agent Processing
       - Strategic Planning: Overall approach and step evaluation
       - Research: Gathering and validating relevant information
       - Analysis: Deep examination and insight generation
       - Quality Control: Evaluation and improvement suggestions
       - Integration: Combining insights and forming conclusions

    3. Synthesis and Review (Coordinator)
       - Integrating agent outputs
       - Ensuring coherence and quality
       - Determining next steps

    Parameters:
        thought (str): The current thinking step. Should be detailed enough for the coordinator 
                      to effectively decompose and delegate to appropriate team members.
        thoughtNumber (int): Current sequence number (≥1)
        totalThoughts (int): Estimated total thoughts needed (≥5)
        nextThoughtNeeded (bool): Whether another thought step is needed
        isRevision (bool, optional): Whether this revises previous thinking
        revisesThought (int, optional): Which thought is being reconsidered
        branchFromThought (int, optional): If branching, which thought number is the branch point
        branchId (str, optional): Branch identifier
        needsMoreThoughts (bool, optional): If more thoughts are needed beyond current estimate

    The thought should be structured to enable effective multi-agent processing:
    - Clear objective or question
    - Context from previous thoughts
    - Specific areas needing different expertise
    - Any constraints or requirements
    - Expected type of output

    Example thought structures:
    - "Analyze [topic] considering: strategic implications, required research, potential risks"
    - "Evaluate the proposal from: technical, resource, and quality perspectives"
    - "Synthesize findings about [topic] from previous research and analysis"
    - "Plan the approach for [task] including: steps, resources, and timeline"

    Returns:
        str: JSON string containing:
            - processedThoughtNumber: The number of the processed thought
            - estimatedTotalThoughts: Current estimate of total thoughts needed
            - nextThoughtNeeded: Whether another thought is needed
            - coordinatedOutput: The synthesized output from the agent team
            - status: Processing status
    """
    global app_context
    
    try:
        # Ensure minimum of 5 thoughts for proper multi-agent analysis
        adjusted_total_thoughts = max(5, totalThoughts)
        if adjusted_total_thoughts != totalThoughts:
            logger.info(f"Adjusted totalThoughts from {totalThoughts} to {adjusted_total_thoughts} to ensure proper analysis depth")
            totalThoughts = adjusted_total_thoughts
        
        # Adjust nextThoughtNeeded based on thoughtNumber and totalThoughts
        adjusted_next_thought_needed = nextThoughtNeeded
        if thoughtNumber < totalThoughts and not nextThoughtNeeded:
            logger.info(f"Adjusted nextThoughtNeeded to True as thoughtNumber ({thoughtNumber}) < totalThoughts ({totalThoughts})")
            adjusted_next_thought_needed = True
        
        input_thought = ThoughtData(
            thought=thought,
            thoughtNumber=thoughtNumber,
            totalThoughts=totalThoughts,
            nextThoughtNeeded=adjusted_next_thought_needed,
            isRevision=isRevision,
            revisesThought=revisesThought,
            branchFromThought=branchFromThought,
            branchId=branchId,
            needsMoreThoughts=needsMoreThoughts
        )
        
        formatted_log_thought = format_thought_for_log(input_thought)
        logger.info(f"\n--- Received Tool Call (Coordinate Mode) ---\n{formatted_log_thought}\n")

        if not app_context or not app_context.team:
            raise Exception("Application context or Agno team not initialized.")

        team_prompt = f"""Process and coordinate the following thought through our specialized agent team:

Thought Number: {input_thought.thoughtNumber} / {input_thought.totalThoughts}
Is Revision: {input_thought.isRevision} (Revises: {input_thought.revisesThought if input_thought.isRevision else 'N/A'})
Is Branch: {input_thought.branchFromThought is not None} (From: {input_thought.branchFromThought if input_thought.branchFromThought else 'N/A'}, ID: {input_thought.branchId if input_thought.branchId else 'N/A'})
Needs More Thoughts Flag: {input_thought.needsMoreThoughts}

Thought Content:
"{input_thought.thought}"

Instruction for Coordinator:
1. First carefully analyze this thought to understand its core objectives and requirements
2. Break this thought into clearly defined subtasks aligned with team members' expertise
3. For each subtask, EXPLICITLY DELEGATE to the appropriate team member by name:
   - Strategic Planner: For planning and step evaluations (assign specific planning subtasks)
   - Information Gatherer: For research and validation tasks (assign specific research questions)
   - Core Analyst: For analytical tasks and insight generation (assign specific analysis areas)
   - Quality Controller: For evaluation and critique tasks (assign specific evaluation criteria)
   - Integration Specialist: For synthesis tasks (assign specific integration objectives)
4. Ensure each team member receives clear instructions with context and expectations
5. After receiving all team member contributions, synthesize them into a coherent, structured response
6. The final output should demonstrate logical flow and comprehensive coverage of all aspects
7. If this is a revision or branch, ensure the appropriate context is incorporated

Success Criteria:
- Effectively break down the thought into appropriate subtasks
- Utilize the unique expertise of each team member
- Ensure comprehensive coverage of all aspects of the thought
- Produce a well-structured, coherent response
- Maintain logical progression throughout the analysis
"""

        logger.debug(f"--- Invoking Agno Team Coordinator (Thought {input_thought.thoughtNumber}) ---")
        team_response = app_context.team.run(team_prompt)
        logger.debug(f"--- Agno Team Coordinated Response (Thought {input_thought.thoughtNumber}) ---\n{team_response}\n")

        response_content = team_response.content if hasattr(team_response, 'content') else str(team_response)

        # Generate additional guidance if this is an early thought and more are needed
        additional_guidance = ""
        if input_thought.thoughtNumber < input_thought.totalThoughts and input_thought.nextThoughtNeeded:
            if input_thought.thoughtNumber == 1:
                additional_guidance = "\n\nGuidance for next steps: Consider focusing on research and data gathering in your next thought."
            elif input_thought.thoughtNumber == 2:
                additional_guidance = "\n\nGuidance for next steps: Now that you have gathered information, focus on deep analysis in your next thought."
            elif input_thought.thoughtNumber < input_thought.totalThoughts - 1:
                additional_guidance = "\n\nGuidance for next steps: Consider evaluating your findings or exploring alternative perspectives in your next thought."
            else:
                additional_guidance = "\n\nGuidance for next steps: Begin synthesizing your analysis and forming conclusions in your next thought."

        result_data = {
            "processedThoughtNumber": input_thought.thoughtNumber,
            "estimatedTotalThoughts": input_thought.totalThoughts,
            "nextThoughtNeeded": input_thought.nextThoughtNeeded,
            "coordinatedOutput": response_content + additional_guidance,
            "status": "success"
        }

        return json.dumps(result_data, indent=2)

    except ValidationError as e:
        logger.error(f"Validation Error processing tool call: {e}")
        raise Exception(f"Input validation failed: {e}")
    except Exception as e:
        logger.error(f"Error processing tool call: {e}")
        raise Exception(f"An unexpected error occurred: {str(e)}")

# --- Main Execution ---

def run():
    """Initializes and runs the MCP server in coordinate mode."""
    logger.info("Initializing Sequential Thinking Server (Coordinate Mode)...")

    global app_context
    # Initialize application resources
    logger.info("Initializing application resources (Coordinate Mode)...")
    team = create_sequential_thinking_team()
    app_context = AppContext(team=team)
    logger.info("Agno team initialized in coordinate mode.")

    try:
        logger.info("Sequential Thinking MCP Server running on stdio (Coordinate Mode)")
        if not app_context:
            logger.critical("FATAL: Application context not initialized.")
            sys.exit(1)
        
        mcp.run(transport="stdio")
    finally:
        logger.info("Shutting down application resources...")
        app_context = None

if __name__ == "__main__":
    if "DEEPSEEK_API_KEY" not in os.environ:
        logger.warning("DEEPSEEK_API_KEY not found.")
    if "EXA_API_KEY" not in os.environ and any(isinstance(t, ExaTools) for a in create_sequential_thinking_team().members for t in getattr(a, 'tools', [])):
         logger.warning("EXA_API_KEY not found, Researcher agent may fail.")

    run()
