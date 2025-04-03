import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from agno.team.team import Team
from agno.tools.exa import ExaTools
from agno.tools.thinking import ThinkingTools
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
    Set up application logging with both file and console handlers.
    Logs will be stored in the user's home directory under .sequential_thinking/logs.

    Returns:
        Logger instance configured with both handlers.
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
    'sequentialthinking' tool.
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
        description="The estimated total thoughts required.",
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
        frozen=True,  # Consider making it mutable if logic needs modification within tool
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
        if v is not None and 'thoughtNumber' in values.data and v >= values.data['thoughtNumber']:
             raise ValueError('revisesThought must be less than thoughtNumber')
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
        # Allow thoughtNumber > totalThoughts for dynamic adjustment downstream
        # revisesThought validation moved to field_validator for better context access
        if self.branchFromThought is not None and self.branchFromThought >= self.thoughtNumber:
            raise ValueError('branchFromThought must be less than thoughtNumber')
        return self

    def dict(self) -> Dict[str, Any]:
        """Convert thought data to dictionary format for serialization"""
        # Use Pydantic's built-in method, handling potential None values if needed
        return self.model_dump(exclude_none=True)


# --- Utility for Formatting Thoughts (for Logging) ---

def format_thought_for_log(thought_data: ThoughtData) -> str:
    """Formats a thought for logging purposes, handling multi-byte characters."""
    prefix = ''
    context = ''
    branch_info_log = '' # Added for explicit branch tracking in log

    if thought_data.isRevision and thought_data.revisesThought is not None:
        prefix = '🔄 Revision'
        context = f' (revising thought {thought_data.revisesThought})'
    elif thought_data.branchFromThought is not None and thought_data.branchId is not None:
        prefix = '🌿 Branch'
        context = f' (from thought {thought_data.branchFromThought}, ID: {thought_data.branchId})'
        # Add visual indication of the branch path in the log
        # This requires accessing the history, let's assume app_context is accessible or passed
        # For simplicity here, we just note it's a branch. More complex viz needs context access.
        branch_info_log = f"Branch Details: ID='{thought_data.branchId}', originates from Thought #{thought_data.branchFromThought}"
    else:
        prefix = '💭 Thought'
        context = ''

    header = f"{prefix} {thought_data.thoughtNumber}/{thought_data.totalThoughts}{context}"

    # Helper to get visual width of a string (approximates multi-byte characters)
    def get_visual_width(s: str) -> int:
        width = 0
        for char in s:
            # Basic approximation: Wide characters (e.g., CJK) take 2 cells, others 1
            if 0x1100 <= ord(char) <= 0x115F or \
               0x2329 <= ord(char) <= 0x232A or \
               0x2E80 <= ord(char) <= 0x3247 or \
               0x3250 <= ord(char) <= 0x4DBF or \
               0x4E00 <= ord(char) <= 0xA4C6 or \
               0xA960 <= ord(char) <= 0xA97C or \
               0xAC00 <= ord(char) <= 0xD7A3 or \
               0xF900 <= ord(char) <= 0xFAFF or \
               0xFE10 <= ord(char) <= 0xFE19 or \
               0xFE30 <= ord(char) <= 0xFE6F or \
               0xFF00 <= ord(char) <= 0xFF60 or \
               0xFFE0 <= ord(char) <= 0xFFE6 or \
               0x1B000 <= ord(char) <= 0x1B001 or \
               0x1F200 <= ord(char) <= 0x1F251 or \
               0x1F300 <= ord(char) <= 0x1F64F or \
               0x1F680 <= ord(char) <= 0x1F6FF:
                width += 2
            else:
                width += 1
        return width

    header_width = get_visual_width(header)
    thought_width = get_visual_width(thought_data.thought)
    max_inner_width = max(header_width, thought_width)
    border_len = max_inner_width + 4 # Accounts for '│ ' and ' │'

    border = '─' * (border_len - 2) # Border width between corners

    # Wrap thought text correctly based on visual width
    thought_lines = []
    current_line = ""
    current_width = 0
    words = thought_data.thought.split()
    for i, word in enumerate(words):
        word_width = get_visual_width(word)
        space_width = 1 if current_line else 0

        if current_width + space_width + word_width <= max_inner_width:
            current_line += (" " if current_line else "") + word
            current_width += space_width + word_width
        else:
            thought_lines.append(current_line)
            current_line = word
            current_width = word_width

        # Add the last line if it exists
        if i == len(words) - 1 and current_line:
             thought_lines.append(current_line)


    # Format lines with padding
    formatted_header = f"│ {header}{' ' * (max_inner_width - header_width)} │"
    formatted_thought_lines = [
        f"│ {line}{' ' * (max_inner_width - get_visual_width(line))} │"
        for line in thought_lines
    ]

    # Include branch info in the log box if applicable
    formatted_branch_info = ''
    if branch_info_log:
        branch_info_width = get_visual_width(branch_info_log)
        padding = ' ' * (max_inner_width - branch_info_width)
        formatted_branch_info = f"\n│ {branch_info_log}{padding} │\n├{'─' * (border_len - 2)}┤"

    return f"""
┌{border}┐
{formatted_header}
├{border}┤
{''.join(formatted_thought_lines)}
{formatted_branch_info} # Insert branch info line here if it exists
└{border}┘"""


# --- Agno Multi-Agent Team Setup ---

def create_sequential_thinking_team() -> Team:
    """
    Creates and configures the Agno multi-agent team for sequential thinking,
    using 'coordinate' mode. The Coordinator delegates tasks to a limited number
    of specialists and synthesizes their results.

    Returns:
        An initialized Team instance.
    """
    try:
        # Use a capable model for all agents and the team coordinator
        model = DeepSeek(id="deepseek-chat")
    except Exception as e:
        logger.error(f"Error initializing base model: {e}")
        logger.error("Please ensure the necessary API keys and configurations are set.")
        sys.exit(1)

    # Create the coordinator agent, now responsible for delegation and synthesis
    coordinator = Agent(
        name="Coordinator",
        role="Task Delegator & Synthesizer",
        description="Coordinates specialist agents to process thoughts by breaking down tasks, delegating to 1-2 relevant experts, and synthesizing their outputs.",
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Coordinator of a specialist team operating in 'coordinate' mode.",
            "Your core responsibilities:",
            " 1. Receive the overall thinking step (thought).",
            " 2. Analyze the thought and break it down into specific sub-tasks suitable for the specialist agents (Planner, Researcher, Analyzer, Critic, Synthesizer).",
            " 3. Identify the 1 or 2 MOST relevant specialists whose expertise is required to address the core aspects of the thought.",
            " 4. Delegate the appropriate sub-task(s) to the selected specialist(s). Provide clear instructions and necessary context for each sub-task.",
            " 5. Await responses from the delegated specialist(s).",
            " 6. Synthesize the responses from the specialist(s) into a single, cohesive, and comprehensive response to the original thought.",
            " 7. Manage the overall flow, considering potential needs for revision or branching based on synthesized results, and incorporating this into the final response.",
            " 8. Ensure the final synthesized response directly addresses the initial thought.",
            "Delegation Criteria:",
            " - Choose specialists based on the primary actions implied by the thought (planning, research, analysis, critique, synthesis).",
            " - **Limit delegation:** Assign sub-tasks to only the 1 or 2 most critical specialists needed for the current thought to ensure efficiency.",
            " - Provide context: Include relevant parts of the original thought or previous context when delegating.",
            "Synthesis:",
            " - Integrate the specialist responses logically.",
            " - Resolve any conflicting information if possible, or highlight discrepancies.",
            " - Formulate a final answer that represents the combined effort.",
            "Remember: Your role is to orchestrate the team's effort effectively and efficiently.",
        ],
        model=model # Use a capable model for coordination
    )

    # Agent definitions adapted for coordinate mode (receive sub-tasks)
    planner = Agent(
        name="Planner",
        role="Strategic Planner",
        description="Develops strategic plans and roadmaps based on delegated sub-tasks.",
        tools=[ThinkingTools()], # Keep for internal scratchpad use if needed
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Strategic Planner specialist.",
            "You will receive specific sub-tasks from the Coordinator related to planning, strategy, or process design.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific planning requirement delegated to you.",
            " 2. Use the `think` tool as a scratchpad if needed to outline your steps or potential non-linear points relevant *to your sub-task*.",
            " 3. Develop the requested plan, roadmap, or sequence of steps.",
            " 4. Identify any potential revision/branching points *specifically related to your plan* and note them.",
            " 5. Consider constraints or potential roadblocks relevant to your assigned task.",
            " 6. Formulate a clear and concise response containing the requested planning output.",
            " 7. Return your response to the Coordinator.",
            "Focus on fulfilling the delegated planning sub-task accurately and efficiently.",
        ],
        model=model,
        add_datetime_to_instructions=True,
        markdown=True
    )

    researcher = Agent(
        name="Researcher",
        role="Information Gatherer",
        description="Gathers and validates information based on delegated research sub-tasks.",
        tools=[ThinkingTools(), ExaTools()], # Keep tools relevant to research
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Information Gatherer specialist.",
            "You will receive specific sub-tasks from the Coordinator requiring information gathering or verification.",
            "**When you receive a sub-task:**",
            " 1. Identify the specific information requested in the delegated task.",
            " 2. Use your tools (like Exa) to find relevant facts, data, or context. Use the `think` tool to plan queries or structure findings if needed.",
            " 3. Validate information where possible.",
            " 4. Structure your findings clearly.",
            " 5. Note any significant information gaps encountered during your research for the specific sub-task.",
            " 6. Formulate a response containing the research findings relevant to the sub-task.",
            " 7. Return your response to the Coordinator.",
            "Focus on accuracy and relevance for the delegated research request.",
        ],
        model=model,
        add_datetime_to_instructions=True,
        markdown=True
    )

    analyzer = Agent(
        name="Analyzer",
        role="Core Analyst",
        description="Performs analysis based on delegated analytical sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Core Analyst specialist.",
            "You will receive specific sub-tasks from the Coordinator requiring analysis, pattern identification, or logical evaluation.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific analytical requirement of the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to outline your analysis framework or draft insights related *to your sub-task*.",
            " 3. Perform the requested analysis (e.g., break down components, identify patterns, evaluate logic).",
            " 4. Generate concise insights based on your analysis of the sub-task.",
            " 5. Based on your analysis, identify any significant logical inconsistencies or invalidated premises *within the scope of your sub-task* that the Coordinator should be aware of for potential revision.",
            " 6. Formulate a response containing your analytical findings and insights.",
            " 7. Return your response to the Coordinator.",
            "Focus on depth and clarity for the delegated analytical task.",
        ],
        model=model,
        add_datetime_to_instructions=True,
        markdown=True
    )

    critic = Agent(
        name="Critic",
        role="Quality Controller",
        description="Critically evaluates ideas or assumptions based on delegated critique sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Quality Controller specialist.",
            "You will receive specific sub-tasks from the Coordinator requiring critique, evaluation of assumptions, or identification of flaws.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific aspect requiring critique in the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to list assumptions or potential weaknesses related *to your sub-task*.",
            " 3. Critically evaluate the provided information or premise as requested.",
            " 4. Identify potential biases, flaws, or logical fallacies within the scope of the sub-task.",
            " 5. Suggest specific improvements or point out weaknesses constructively.",
            " 6. If your critique reveals significant flaws or outdated assumptions *within the scope of your sub-task*, highlight this clearly in your response for the Coordinator to consider for potential revision.",
            " 7. Formulate a response containing your critical evaluation and recommendations.",
            " 8. Return your response to the Coordinator.",
            "Focus on rigorous and constructive critique for the delegated evaluation task.",
        ],
        model=model,
        add_datetime_to_instructions=True,
        markdown=True
    )

    synthesizer = Agent(
        name="Synthesizer",
        role="Integration Specialist",
        description="Integrates information or forms conclusions based on delegated synthesis sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "You are the Integration Specialist.",
            "You will receive specific sub-tasks from the Coordinator requiring integration of information, synthesis of ideas, or formation of conclusions.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific elements needing integration or synthesis in the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to outline connections or draft conclusions related *to your sub-task*.",
            " 3. Connect the provided elements, identify overarching themes, or draw conclusions as requested.",
            " 4. Distill complex inputs into clear, structured insights for the sub-task.",
            " 5. Formulate a response presenting the synthesized information or conclusions.",
            " 6. Return your response to the Coordinator.",
            "Focus on creating clarity and coherence for the delegated synthesis task.",
        ],
        model=model,
        add_datetime_to_instructions=True,
        markdown=True
    )

    # Create the team with coordinate mode and context sharing enabled
    team = Team(
        name="SequentialThinkingTeam",
        mode="coordinate", # Changed to coordinate
        members=[planner, researcher, analyzer, critic, synthesizer],
        # Use the Coordinator agent as the primary interface in coordinate mode
        description="A multi-agent team using coordination to process thoughts. The Coordinator delegates tasks to 1-2 specialists and synthesizes results.",
        success_criteria=[
            "Break down thoughts into appropriate sub-tasks",
            "Delegate sub-tasks efficiently to the 1-2 most relevant specialists",
            "Specialists execute delegated sub-tasks accurately",
            "Coordinator synthesizes specialist responses into a cohesive final output",
            "Maintain logical progression, potentially identifying needs for revision/branching during synthesis"
        ],
        enable_agentic_context=True, # Enable shared context management by coordinator
        share_member_interactions=True, # Allow members' interactions to be shared in context
        markdown=True,
        debug_mode=True
    )

    return team

# --- Application Context and Lifespan Management ---

@dataclass
class AppContext:
    """Holds shared application resources, like the Agno team."""
    team: Team
    thought_history: List[ThoughtData] = field(default_factory=list)
    branches: Dict[str, List[ThoughtData]] = field(default_factory=dict)
    
    def add_thought(self, thought: ThoughtData) -> None:
        """Add a thought to history and manage branches"""
        self.thought_history.append(thought)
        
        # Handle branching
        if thought.branchFromThought is not None and thought.branchId is not None:
            if thought.branchId not in self.branches:
                self.branches[thought.branchId] = []
            self.branches[thought.branchId].append(thought)
    
    def get_branch_thoughts(self, branch_id: str) -> List[ThoughtData]:
        """Get all thoughts in a specific branch"""
        return self.branches.get(branch_id, [])
    
    def get_all_branches(self) -> Dict[str, int]:
        """Get all branch IDs and their thought counts"""
        return {branch_id: len(thoughts) for branch_id, thoughts in self.branches.items()}

app_context: Optional[AppContext] = None

@asynccontextmanager
async def app_lifespan() -> AsyncIterator[None]:
    """Manages the application lifecycle."""
    global app_context
    logger.info("Initializing application resources (Route Mode)...")
    team = create_sequential_thinking_team()
    app_context = AppContext(team=team)
    logger.info("Agno team initialized in route mode.")
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
    """
    Starter prompt for sequential thinking that ENCOURAGES non-linear exploration.
    """
    # Define mandatory checkpoints - REMOVED
    # revision_checkpoint = 4 # Must have at least one revision by thought #4 - REMOVED
    # branch_checkpoint = 5   # Must have at least one branch by thought #5 - REMOVED
    # min_thoughts = max(5, branch_checkpoint) # Ensure total thoughts accommodates checkpoints - ADJUSTED
    min_thoughts = 5 # Set a reasonable minimum number of initial thoughts

    prompt_text = f"""Initiate a comprehensive sequential thinking process for the following problem:

Problem: {problem}
{f'Context: {context}' if context else ''}

**Sequential Thinking Goals & Guidelines:**

1.  **Estimate Steps:** Analyze the problem complexity. Your initial `totalThoughts` estimate should be at least {min_thoughts}.
2.  **First Thought:** Call the 'sequentialthinking' tool with `thoughtNumber: 1`, your estimated `totalThoughts` (at least {min_thoughts}), and `nextThoughtNeeded: True`. Structure your first thought as: "Plan a comprehensive analysis approach for: {problem}"
3.  **Encouraged Revision:** Actively look for opportunities to revise previous thoughts if you identify flaws, oversights, or necessary refinements based on later analysis (especially from the Critic or Analyzer). Use `isRevision: True` and `revisesThought: <thought_number>` when performing a revision. While not strictly enforced at a specific step, robust thinking often involves self-correction.
4.  **Encouraged Branching:** Explore alternative paths, perspectives, or solutions where appropriate. Use `branchFromThought: <thought_number>` and `branchId: <unique_branch_name>` to initiate branches. Exploring alternatives is key to thorough analysis. Consider suggestions for branching proposed by the specialist agents.
5.  **Extension:** If the analysis requires more steps than initially estimated, use `needsMoreThoughts: True` on the thought *before* you need the extension.
6.  **Thought Content:** Each thought must:
    *   Be detailed and specific to the current stage (planning, analysis, critique, synthesis, revision, branching).
    *   Clearly explain the *reasoning* behind the thought, especially for revisions and branches.
    *   Conclude by outlining what the *next* thought needs to address to fulfill the overall plan.

**Process:**

*   The `sequentialthinking` tool will track your progress. Specialist agents (Analyzer, Critic) are specifically tasked with identifying potential needs for revision.
*   Focus on insightful analysis, constructive critique (leading to potential revisions), and creative exploration (leading to potential branching).
*   Actively reflect on the process. Linear thinking might be insufficient for complex problems. Proceed with the first thought."""

    return {
        "description": "Mandatory non-linear sequential thinking starter prompt (route mode)",
        "messages": [{"role": "user", "content": {"type": "text", "text": prompt_text}}]
    }

async def process_agent_tasks(team: Team, input_thought: ThoughtData) -> Dict[str, str]:
    """
    Process a thought using route mode - determine the most appropriate agent
    and route the thought to that agent. Includes dynamic prompts for revision checks.

    Args:
        team: The Agno team containing all agents
        input_thought: The thought data to process

    Returns:
        Dictionary containing result from the selected agent
    """
    logger.info("Starting thought routing process")
    specialist_name = "analyzer" # Default

    # Determine specialist based on thought type and keywords
    # (Keep existing revision/branch routing hints, but don't default route solely based on isRevision)
    if input_thought.isRevision and input_thought.revisesThought is not None:
        logger.info(f"Processing revision of thought #{input_thought.revisesThought}")
        # Hint towards critic/analyzer for revisions, but keyword matching can override
        thought_lower = input_thought.thought.lower()
        if "critique" in thought_lower or "evaluate" in thought_lower:
             specialist_name = "critic"
        elif "analyze" in thought_lower or "reanalyze" in thought_lower:
             specialist_name = "analyzer"
        # Let keyword matching handle other cases or default

    elif input_thought.branchFromThought is not None and input_thought.branchId is not None:
        logger.info(f"Processing branch from thought #{input_thought.branchFromThought} (ID: {input_thought.branchId})")
        # Hint towards planner/analyzer for branches
        thought_lower = input_thought.thought.lower()
        if "plan" in thought_lower or "strateg" in thought_lower: # strateg for strategy
             specialist_name = "planner"
        elif "analy" in thought_lower: # analy for analyze/analysis
             specialist_name = "analyzer"
        # Let keyword matching handle other cases or default

    # Standard thought routing based on keywords if not revision/branch override
    # (Use existing keyword logic to determine specialist_name)
    thought_lower = input_thought.thought.lower()

    # Keyword sets for each specialist
    planning_keywords = ["plan", "strategy", "approach", "steps", "method", "roadmap", "design", "framework", "prepare", "schedule"]
    research_keywords = ["research", "information", "data", "find", "search", "explore", "discover", "facts", "statistics", "evidence"]
    analysis_keywords = ["analyze", "analysis", "examine", "investigate", "understand", "breakdown", "interpret", "reason", "logic", "patterns", "reanalyze"]
    critique_keywords = ["evaluate", "assess", "critique", "review", "examine", "judge", "weakness", "flaw", "limitation", "improve", "challenge", "bias"]
    synthesis_keywords = ["synthesize", "integrate", "combine", "consolidate", "conclude", "summarize", "unify", "merge", "overall", "big picture"]

    # Count keyword matches for each specialist
    specialist_scores = {
        "planner": sum(1 for keyword in planning_keywords if keyword in thought_lower),
        "researcher": sum(1 for keyword in research_keywords if keyword in thought_lower),
        "analyzer": sum(1 for keyword in analysis_keywords if keyword in thought_lower),
        "critic": sum(1 for keyword in critique_keywords if keyword in thought_lower),
        "synthesizer": sum(1 for keyword in synthesis_keywords if keyword in thought_lower)
    }

    # Refined logic for determining the specialist
    # Prioritize explicit keywords, then handle default cases/hints
    highest_score = max(specialist_scores.values())
    best_specialists = [name for name, score in specialist_scores.items() if score == highest_score]

    if highest_score > 0 and len(best_specialists) == 1:
        specialist_name = best_specialists[0]
    elif highest_score > 0 and len(best_specialists) > 1:
        # Handle ties (e.g., prioritize based on thought type or default)
        if input_thought.isRevision and "critic" in best_specialists:
            specialist_name = "critic"
        elif input_thought.isRevision and "analyzer" in best_specialists:
            specialist_name = "analyzer"
        elif input_thought.branchFromThought is not None and "planner" in best_specialists:
            specialist_name = "planner"
        elif input_thought.branchFromThought is not None and "analyzer" in best_specialists:
            specialist_name = "analyzer"
        else:
            # Default tie-breaker (e.g., Analyzer or a predefined order)
            specialist_name = "analyzer" # Or choose from best_specialists based on some priority
    else: # No keywords matched
        if input_thought.isRevision:
            specialist_name = "critic" # Default for revision if no keywords
        elif input_thought.branchFromThought is not None:
            specialist_name = "planner" # Default for branch if no keywords
        elif input_thought.thoughtNumber == 1:
            specialist_name = "planner" # First thought usually planning
        elif input_thought.thoughtNumber == input_thought.totalThoughts and not input_thought.needsMoreThoughts:
             specialist_name = "synthesizer" # Last thought usually synthesis
        else:
            specialist_name = "analyzer" # Default middle thoughts to analyzer


    # Map specialist name to agent index
    specialist_map = {
        "planner": 0,
        "researcher": 1,
        "analyzer": 2,
        "critic": 3,
        "synthesizer": 4
    }
    agent_index = specialist_map.get(specialist_name, 2)  # Default to analyzer
    selected_agent = team.members[agent_index]

    logger.info(f"Routing thought to: {selected_agent.name}")

    # --- Dynamic Prompt Enhancement ---
    dynamic_instructions = ""
    # Add revision check prompt primarily for Critic and Analyzer
    if selected_agent.name in ["Critic", "Analyzer"] and input_thought.thoughtNumber > 1:
        # Provide context from previous thoughts if available and relevant
        history_context = ""
        if len(app_context.thought_history) > 0:
             # Simple context: just mention previous thought exists
             history_context = f"Context: Consider this in light of thought #{input_thought.thoughtNumber-1} and potentially earlier thoughts."
             # More complex context could be added here if needed, e.g., summarizing relevant previous points

        dynamic_instructions = f"""
        {history_context}
        **Additional Task: Revision Check**
        Carefully review your analysis/critique. Does it reveal significant issues (flaws, invalidated assumptions, logical gaps) in *any previous thought* that necessitate a formal revision?
        If YES, you MUST include a specific recommendation in your response using the exact format:
        'RECOMMENDATION: Revise thought #X (using isRevision=True, revisesThought=X) because [your reason]'.
        If NO, simply proceed with your primary analysis/critique.
        """

    # Original thought context (revision/branch info)
    original_thought_context = ""
    if input_thought.isRevision and input_thought.revisesThought is not None:
        for hist_thought in app_context.thought_history:
            if hist_thought.thoughtNumber == input_thought.revisesThought:
                original_thought_context = f"\nCONTEXT: This thought REVISES thought #{input_thought.revisesThought}: \"{hist_thought.thought}\""
                break

    branch_context = ""
    if input_thought.branchFromThought is not None and input_thought.branchId is not None:
        for hist_thought in app_context.thought_history:
            if hist_thought.thoughtNumber == input_thought.branchFromThought:
                branch_context = f"\nCONTEXT: This thought is a BRANCH from thought #{input_thought.branchFromThought}: \"{hist_thought.thought}\" (Branch ID: {input_thought.branchId})"
                break

    # Determine focus based on thought type
    if input_thought.isRevision:
        revision_focus = "focus on executing the revision based on the original thought and the current instruction"
    elif input_thought.branchFromThought is not None:
        revision_focus = "focus on exploring this alternative path thoroughly"
    else:
        revision_focus = "address this thought comprehensively according to your role"

    # Construct final prompt
    prompt = f"""
    As the {selected_agent.name} ({selected_agent.role}), process the following thought:

    THOUGHT: "{input_thought.thought}"

    {original_thought_context}
    {branch_context}

    Your primary objective is to {revision_focus}.

    {dynamic_instructions}

    Follow the response structure outlined in your general instructions.
    """

    # Get response from selected agent
    response = await selected_agent.arun(prompt)
    result = response.content if hasattr(response, 'content') else str(response)

    # Suggestion for *branching* in future thoughts (Revision suggestion now comes *from* the agent)
    suggestion = ""
    if input_thought.nextThoughtNeeded and input_thought.thoughtNumber < input_thought.totalThoughts:
        branch_indicators = [
            "alternative", "another approach", "different method", "another possibility",
            "different perspective", "other option", "could also", "different direction",
            "two paths", "multiple ways", "fork in", "different strategies"
        ]
        # Check only for branch indicators in the agent's *direct response* (excluding explicit revision recommendations)
        response_lower = result.lower()
        # Basic check to avoid matching the recommendation format itself
        if "recommendation: revise thought #" not in response_lower:
            if any(indicator in response_lower for indicator in branch_indicators):
                 suggestion = "\n\n**SUGGESTION**: This analysis mentions alternatives. Consider using `branchFromThought: X` and `branchId: \"alternative-Y\"` in a future thought to explore one."

    agent_results = {
        selected_agent.name.lower(): result + suggestion
    }

    logger.info(f"Completed processing with {selected_agent.name}")
    return agent_results

@mcp.tool()
async def sequentialthinking(thought: str, thoughtNumber: int, totalThoughts: int, nextThoughtNeeded: bool,
                      isRevision: bool = False, revisesThought: Optional[int] = None,
                      branchFromThought: Optional[int] = None, branchId: Optional[str] = None,
                      needsMoreThoughts: bool = False) -> str:
    """
    Processes one step in a sequential thinking chain, relying on agent analysis for revisions/branching.

    This tool routes thoughts to specialist agents. Agents (esp. Critic, Analyzer)
    are instructed to SUGGEST revisions if prior thoughts have issues. Branching is
    encouraged based on analysis and suggestions.

    Parameters:
        thought (str): The current thinking step.
        thoughtNumber (int): Current sequence number (≥1)
        totalThoughts (int): Estimated total thoughts needed (≥5 suggested)
        nextThoughtNeeded (bool): Whether another thought step is needed
        isRevision (bool, optional): Whether this revises previous thinking
        revisesThought (int, optional): Which thought is being reconsidered
        branchFromThought (int, optional): If branching, which thought number is the branch point
        branchId (str, optional): Branch identifier
        needsMoreThoughts (bool, optional): If more thoughts are needed beyond current estimate

    Returns:
        str: JSON string containing processing results and status.
    """
    global app_context
    if not app_context or not app_context.team:
        logger.error("Application context or Agno team not initialized during tool call.")
        raise Exception("Critical Error: Application context not available.")

    # --- Enforcement Constants (Removed) ---
    # REVISION_CHECKPOINT = 4 # Removed
    # BRANCH_CHECKPOINT = 5 # Removed
    MIN_TOTAL_THOUGHTS = 5 # Keep a minimum suggestion

    # enforcement_override_reason = None # Removed related to revision/branch enforcement

    try:
        # --- Initial Validation and Adjustments ---
        adjusted_total_thoughts = max(MIN_TOTAL_THOUGHTS, totalThoughts)
        if adjusted_total_thoughts != totalThoughts:
            # Make this a less severe log message, as it's now a suggestion
            logger.info(f"Initial totalThoughts ({totalThoughts}) is below suggested minimum {MIN_TOTAL_THOUGHTS}. Proceeding, but consider if more steps might be needed.")
            # We won't force adjustment anymore: totalThoughts = adjusted_total_thoughts
            # Let the LLM manage the estimate, but log the suggestion.

        # Ensure nextThoughtNeeded is consistent
        adjusted_next_thought_needed = nextThoughtNeeded
        # Allow LLM to signal end even if thoughtNumber < totalThoughts
        # if thoughtNumber < totalThoughts and not nextThoughtNeeded and not needsMoreThoughts:
        #      logger.warning(f"Adjusted nextThoughtNeeded to True as thoughtNumber ({thoughtNumber}) < totalThoughts ({totalThoughts}) and not extending.")
        #      adjusted_next_thought_needed = True
        if thoughtNumber >= totalThoughts and not needsMoreThoughts:
             # If we reach the estimated end and are not requesting more, ensure next is False.
             adjusted_next_thought_needed = False

        # If extending, ensure totalThoughts increases and next is needed
        if needsMoreThoughts and thoughtNumber >= totalThoughts:
            totalThoughts = thoughtNumber + 2  # Extend by at least 2
            logger.info(f"Extended totalThoughts to {totalThoughts} due to needsMoreThoughts flag.")
            adjusted_next_thought_needed = True # Ensure we continue

        # Create ThoughtData instance *after* initial adjustments
        current_input_thought = ThoughtData(
            thought=thought,
            thoughtNumber=thoughtNumber,
            totalThoughts=totalThoughts, # Use original or extended totalThoughts
            nextThoughtNeeded=adjusted_next_thought_needed,
            isRevision=isRevision,
            revisesThought=revisesThought,
            branchFromThought=branchFromThought,
            branchId=branchId,
            needsMoreThoughts=needsMoreThoughts # Preserve flag
        )

        # --- Mandatory Action Enforcement (REMOVED) ---
        # history = app_context.thought_history # Get current history
        enforcement_override_reason = None # Reset / Remove

        # Check for Mandatory Revision (REMOVED)
        # ... removed revision enforcement block ...

        # Check for Mandatory Branch (REMOVED)
        # ... removed branch enforcement block ...


        # --- Logging and History Update ---
        log_prefix = "--- Received Thought ---"
        if current_input_thought.isRevision:
            log_prefix = f"--- Received REVISION Thought (revising #{current_input_thought.revisesThought}) ---"
        elif current_input_thought.branchFromThought is not None:
            log_prefix = f"--- Received BRANCH Thought (from #{current_input_thought.branchFromThought}, ID: {current_input_thought.branchId}) ---"
        # Removed enforcement logging: if enforcement_override_reason: ...

        formatted_log_thought = format_thought_for_log(current_input_thought)
        logger.info(f"\n{log_prefix}\n{formatted_log_thought}\n")

        # Add the thought to history
        app_context.add_thought(current_input_thought)

        # --- Process Thought with Agent ---
        # Pass the thought to the agent processing function
        agent_results = await process_agent_tasks(app_context.team, current_input_thought)

        specialist = list(agent_results.keys())[0]
        specialist_response = agent_results[specialist]

        # --- Guidance for Next Step (Revised) ---
        additional_guidance = "\n\nGuidance for next step:"
        next_thought_num = current_input_thought.thoughtNumber + 1
        # history_after_add = app_context.thought_history # Get history *including* current thought

        # Check future requirements (Removed mandatory checks)
        # needs_revision_soon = ... # Removed
        # needs_branch_soon = ... # Removed

        # Guidance logic refinement
        if not current_input_thought.nextThoughtNeeded:
             additional_guidance = "\n\nThis is the final thought based on current estimates or your signal. Ensure all analyses are complete and conclusions are synthesized."
        else:
            # Guidance based on current thought type
            if current_input_thought.isRevision:
                additional_guidance += " Reflect on this revision. Does it resolve the identified issue? Does it necessitate further analysis or branching based on the new understanding?"
            elif current_input_thought.branchFromThought is not None:
                additional_guidance += f" Continue exploring branch '{current_input_thought.branchId}'. How does this alternative path compare to the main line or other branches? Consider evaluating its viability or synthesizing findings later."
            else:
                 additional_guidance += " Continue the process. Address the core task of the next thought (e.g., analysis, planning, synthesis)."

            # Universal reminder about agent suggestions for revision and branching
            additional_guidance += "\n**Reminder:** Carefully check the specialist's response above. "
            additional_guidance += "If they recommended revising a previous thought (using 'RECOMMENDATION: Revise thought #X...'), strongly consider using the `isRevision` and `revisesThought` parameters in your next call. "
            additional_guidance += "Also, consider any suggestions for branching (e.g., using `branchFromThought` and `branchId`) to explore mentioned alternatives."
            additional_guidance += "\n**ToT Principle:** Consider if the current problem stage warrants exploring multiple alternatives simultaneously. If so, you could initiate parallel branches (using distinct `branchId`s originating from the same `branchFromThought`) in subsequent steps to represent different reasoning paths, aiming for later evaluation/synthesis."


        # --- Build Result ---
        result_data = {
            "processedThoughtNumber": current_input_thought.thoughtNumber,
            "estimatedTotalThoughts": current_input_thought.totalThoughts,
            "nextThoughtNeeded": current_input_thought.nextThoughtNeeded,
            "specialist": specialist,
            "response": specialist_response + additional_guidance, # Add updated guidance
            "branches": list(app_context.branches.keys()),
            "thoughtHistoryLength": len(app_context.thought_history),
            "branchDetails": {
                "currentBranchId": current_input_thought.branchId if current_input_thought.branchFromThought is not None else "main",
                "branchOriginThought": current_input_thought.branchFromThought,
                "allBranches": app_context.get_all_branches() # Include counts
            },
            "isRevision": current_input_thought.isRevision,
            "revisesThought": current_input_thought.revisesThought if current_input_thought.isRevision else None,
            "isBranch": current_input_thought.branchFromThought is not None,
            "status": "success"
        }

        return json.dumps(result_data, indent=2)

    except ValidationError as e:
        logger.error(f"Validation Error processing tool call: {e}")
        # Provide detailed validation error back to the caller
        return json.dumps({
            "error": f"Input validation failed: {e}",
            "status": "validation_error"
        }, indent=2)
    except Exception as e:
        logger.exception(f"Error processing tool call") # Log full traceback
        return json.dumps({
            "error": f"An unexpected error occurred: {str(e)}",
            "status": "failed"
        }, indent=2)

# --- Main Execution ---

def run():
    """Initializes and runs the MCP server in route mode."""
    logger.info("Initializing Sequential Thinking Server (Route Mode)...")

    global app_context
    # Initialize application resources
    logger.info("Initializing application resources (Route Mode)...")
    team = create_sequential_thinking_team()
    app_context = AppContext(team=team)
    logger.info("Agno team initialized in route mode.")

    try:
        logger.info("Sequential Thinking MCP Server running on stdio (Route Mode)")
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
