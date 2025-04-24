import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from mcp.server.fastmcp import FastMCP
from agno.agent import Agent
from agno.models.base import Model
from agno.models.deepseek import DeepSeek
from agno.models.groq import Groq
from agno.models.openrouter import OpenRouter
from agno.team.team import Team
from agno.tools.exa import ExaTools
from agno.tools.thinking import ThinkingTools
from dotenv import load_dotenv
from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)

import logging
import logging.handlers
from pathlib import Path

load_dotenv()

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

logger = setup_logging()

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
    """Formats a thought for simpler logging purposes."""
    prefix = ''
    context = ''
    branch_info_log = ''

    if thought_data.isRevision and thought_data.revisesThought is not None:
        prefix = 'Revision'
        context = f' (revising thought {thought_data.revisesThought})'
    elif thought_data.branchFromThought is not None and thought_data.branchId is not None:
        prefix = 'Branch'
        context = f' (from thought {thought_data.branchFromThought}, ID: {thought_data.branchId})'
        branch_info_log = f"  Branch Details: ID='{thought_data.branchId}', originates from Thought #{thought_data.branchFromThought}"
    else:
        prefix = 'Thought'
        context = ''

    header = f"{prefix} {thought_data.thoughtNumber}/{thought_data.totalThoughts}{context}"

    log_entry = f"{header}\n"
    log_entry += f"  Thought: {thought_data.thought}\n"
    if branch_info_log:
        log_entry += f"{branch_info_log}\n"
    log_entry += f"  Next Needed: {thought_data.nextThoughtNeeded}, Needs More: {thought_data.needsMoreThoughts}"

    return log_entry


# --- Agno Multi-Agent Team Setup ---

def get_model_config() -> tuple[Type[Model], str, str]:
    """
    Determines the LLM provider, team model ID, and agent model ID based on environment variables.

    Returns:
        A tuple containing:
        - ModelClass: The Agno model class (e.g., DeepSeek, Groq, OpenRouter).
        - team_model_id: The model ID for the team coordinator.
        - agent_model_id: The model ID for the specialist agents.
    """
    provider = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    logger.info(f"Selected LLM Provider: {provider}")

    if provider == "deepseek":
        ModelClass = DeepSeek
        # Use environment variables for DeepSeek model IDs if set, otherwise use defaults
        team_model_id = os.environ.get("DEEPSEEK_TEAM_MODEL_ID", "deepseek-chat")
        agent_model_id = os.environ.get("DEEPSEEK_AGENT_MODEL_ID", "deepseek-chat")
        logger.info(f"Using DeepSeek: Team Model='{team_model_id}', Agent Model='{agent_model_id}'")
    elif provider == "groq":
        ModelClass = Groq
        team_model_id = os.environ.get("GROQ_TEAM_MODEL_ID", "deepseek-r1-distill-llama-70b")
        agent_model_id = os.environ.get("GROQ_AGENT_MODEL_ID", "qwen-2.5-32b")
        logger.info(f"Using Groq: Team Model='{team_model_id}', Agent Model='{agent_model_id}'")
    elif provider == "openrouter":
        ModelClass = OpenRouter
        team_model_id = os.environ.get("OPENROUTER_TEAM_MODEL_ID", "deepseek/deepseek-chat-v3-0324")
        agent_model_id = os.environ.get("OPENROUTER_AGENT_MODEL_ID", "deepseek/deepseek-r1")
        logger.info(f"Using OpenRouter: Team Model='{team_model_id}', Agent Model='{agent_model_id}'")
    else:
        logger.error(f"Unsupported LLM_PROVIDER: {provider}. Defaulting to DeepSeek.")
        ModelClass = DeepSeek
        team_model_id = "deepseek-chat"
        agent_model_id = "deepseek-chat"

    return ModelClass, team_model_id, agent_model_id


def create_sequential_thinking_team() -> Team:
    """
    Creates and configures the Agno multi-agent team for sequential thinking,
    using 'coordinate' mode. The Team object itself acts as the coordinator.

    Returns:
        An initialized Team instance.
    """
    try:
        ModelClass, team_model_id, agent_model_id = get_model_config()
        team_model_instance = ModelClass(id=team_model_id)
        agent_model_instance = ModelClass(id=agent_model_id)

    except Exception as e:
        logger.error(f"Error initializing models: {e}")
        logger.error("Please ensure the necessary API keys and configurations are set for the selected provider ({os.environ.get('LLM_PROVIDER', 'deepseek')}).")
        sys.exit(1)

    # REMOVED the separate Coordinator Agent definition.
    # The Team object below will handle coordination using its own instructions/model.

    # Agent definitions for specialists
    planner = Agent(
        name="Planner",
        role="Strategic Planner",
        description="Develops strategic plans and roadmaps based on delegated sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            "You are the Strategic Planner specialist.",
            "You will receive specific sub-tasks from the Team Coordinator related to planning, strategy, or process design.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific planning requirement delegated to you.",
            " 2. Use the `think` tool as a scratchpad if needed to outline your steps or potential non-linear points relevant *to your sub-task*.",
            " 3. Develop the requested plan, roadmap, or sequence of steps.",
            " 4. Identify any potential revision/branching points *specifically related to your plan* and note them.",
            " 5. Consider constraints or potential roadblocks relevant to your assigned task.",
            " 6. Formulate a clear and concise response containing the requested planning output.",
            " 7. Return your response to the Team Coordinator.",
            "Focus on fulfilling the delegated planning sub-task accurately and efficiently.",
        ],
        model=agent_model_instance, # Use the designated agent model
        add_datetime_to_instructions=True,
        markdown=True
    )

    researcher = Agent(
        name="Researcher",
        role="Information Gatherer",
        description="Gathers and validates information based on delegated research sub-tasks.",
        tools=[ThinkingTools(), ExaTools()],
        instructions=[
            "You are the Information Gatherer specialist.",
            "You will receive specific sub-tasks from the Team Coordinator requiring information gathering or verification.",
            "**When you receive a sub-task:**",
            " 1. Identify the specific information requested in the delegated task.",
            " 2. Use your tools (like Exa) to find relevant facts, data, or context. Use the `think` tool to plan queries or structure findings if needed.",
            " 3. Validate information where possible.",
            " 4. Structure your findings clearly.",
            " 5. Note any significant information gaps encountered during your research for the specific sub-task.",
            " 6. Formulate a response containing the research findings relevant to the sub-task.",
            " 7. Return your response to the Team Coordinator.",
            "Focus on accuracy and relevance for the delegated research request.",
        ],
        model=agent_model_instance, # Use the designated agent model
        add_datetime_to_instructions=True,
        markdown=True
    )

    analyzer = Agent(
        name="Analyzer",
        role="Core Analyst",
        description="Performs analysis based on delegated analytical sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            "You are the Core Analyst specialist.",
            "You will receive specific sub-tasks from the Team Coordinator requiring analysis, pattern identification, or logical evaluation.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific analytical requirement of the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to outline your analysis framework or draft insights related *to your sub-task*.",
            " 3. Perform the requested analysis (e.g., break down components, identify patterns, evaluate logic).",
            " 4. Generate concise insights based on your analysis of the sub-task.",
            " 5. Based on your analysis, identify any significant logical inconsistencies or invalidated premises *within the scope of your sub-task* that you should highlight in your response.",
            " 6. Formulate a response containing your analytical findings and insights.",
            " 7. Return your response to the Team Coordinator.",
            "Focus on depth and clarity for the delegated analytical task.",
        ],
        model=agent_model_instance, # Use the designated agent model
        add_datetime_to_instructions=True,
        markdown=True
    )

    critic = Agent(
        name="Critic",
        role="Quality Controller",
        description="Critically evaluates ideas or assumptions based on delegated critique sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            "You are the Quality Controller specialist.",
            "You will receive specific sub-tasks from the Team Coordinator requiring critique, evaluation of assumptions, or identification of flaws.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific aspect requiring critique in the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to list assumptions or potential weaknesses related *to your sub-task*.",
            " 3. Critically evaluate the provided information or premise as requested.",
            " 4. Identify potential biases, flaws, or logical fallacies within the scope of the sub-task.",
            " 5. Suggest specific improvements or point out weaknesses constructively.",
            " 6. If your critique reveals significant flaws or outdated assumptions *within the scope of your sub-task*, highlight this clearly in your response.",
            " 7. Formulate a response containing your critical evaluation and recommendations.",
            " 8. Return your response to the Team Coordinator.",
            "Focus on rigorous and constructive critique for the delegated evaluation task.",
        ],
        model=agent_model_instance, # Use the designated agent model
        add_datetime_to_instructions=True,
        markdown=True
    )

    synthesizer = Agent(
        name="Synthesizer",
        role="Integration Specialist",
        description="Integrates information or forms conclusions based on delegated synthesis sub-tasks.",
        tools=[ThinkingTools()],
        instructions=[
            "You are the Integration Specialist.",
            "You will receive specific sub-tasks from the Team Coordinator requiring integration of information, synthesis of ideas, or formation of conclusions.",
            "**When you receive a sub-task:**",
            " 1. Understand the specific elements needing integration or synthesis in the delegated task.",
            " 2. Use the `think` tool as a scratchpad if needed to outline connections or draft conclusions related *to your sub-task*.",
            " 3. Connect the provided elements, identify overarching themes, or draw conclusions as requested.",
            " 4. Distill complex inputs into clear, structured insights for the sub-task.",
            " 5. Formulate a response presenting the synthesized information or conclusions.",
            " 6. Return your response to the Team Coordinator.",
            "Focus on creating clarity and coherence for the delegated synthesis task.",
            "**For the final synthesis task provided by the Coordinator:** Aim for a concise and high-level integration. Focus on the core synthesized understanding and key takeaways, rather than detailing the step-by-step process or extensive analysis of each component.",
        ],
        model=agent_model_instance, # Use the designated agent model
        add_datetime_to_instructions=True,
        markdown=True
    )

    # Create the team with coordinate mode.
    # The Team object itself acts as the coordinator, using the instructions/description/model provided here.
    team = Team(
        name="SequentialThinkingTeam",
        mode="coordinate",
        members=[planner, researcher, analyzer, critic, synthesizer], # ONLY specialist agents
        model=team_model_instance, # Model for the Team's coordination logic
        description="You are the Coordinator of a specialist team processing sequential thoughts. Your role is to manage the flow, delegate tasks, and synthesize results.",
        instructions=[
            "You are the Coordinator managing a team of specialists (Planner, Researcher, Analyzer, Critic, Synthesizer) in 'coordinate' mode.",
            "Your core responsibilities when receiving an input thought:",
            " 1. Analyze the input thought, considering its type (e.g., initial planning, analysis, revision, branch).",
            " 2. Break the thought down into specific, actionable sub-tasks suitable for your specialist team members.",
            " 3. Determine the MINIMUM set of specialists required to address the thought comprehensively.",
            " 4. Delegate the appropriate sub-task(s) ONLY to the essential specialists identified. Provide clear instructions and necessary context (like previous thought content if revising/branching) for each sub-task.",
            " 5. Await responses from the delegated specialist(s).",
            " 6. Synthesize the responses from the specialist(s) into a single, cohesive, and comprehensive response addressing the original input thought.",
            " 7. Based on the synthesis and specialist feedback, identify potential needs for revision of previous thoughts or branching to explore alternatives.",
            " 8. Include clear recommendations in your final synthesized response if revision or branching is needed. Use formats like 'RECOMMENDATION: Revise thought #X...' or 'SUGGESTION: Consider branching from thought #Y...'.",
            " 9. Ensure the final synthesized response directly addresses the initial input thought and provides necessary guidance for the next step in the sequence.",
            "Delegation Criteria:",
            " - Choose specialists based on the primary actions implied by the thought (planning, research, analysis, critique, synthesis).",
            " - **Prioritize Efficiency:** Delegate sub-tasks only to specialists whose expertise is *strictly necessary*. Aim to minimize concurrent delegations.",
            " - Provide context: Include relevant parts of the input thought or previous context when delegating.",
            "Synthesis:",
            " - Integrate specialist responses logically.",
            " - Resolve conflicts or highlight discrepancies.",
            " - Formulate a final answer representing the combined effort.",
            "Remember: Orchestrate the team effectively and efficiently."
        ],
        success_criteria=[
            "Break down input thoughts into appropriate sub-tasks",
            "Delegate sub-tasks efficiently to the most relevant specialists",
            "Specialists execute delegated sub-tasks accurately",
            "Synthesize specialist responses into a cohesive final output addressing the original thought",
            "Identify and recommend necessary revisions or branches based on analysis"
        ],
        enable_agentic_context=False, # Allows context sharing managed by the Team (coordinator)
        share_member_interactions=False, # Allows members' interactions to be shared
        markdown=True,
        debug_mode=False,
        add_datetime_to_instructions=True
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
    logger.info("Initializing application resources (Coordinate Mode)...")
    try:
        team = create_sequential_thinking_team()
        app_context = AppContext(team=team)
        provider = os.environ.get("LLM_PROVIDER", "deepseek").lower()
        logger.info(f"Agno team initialized in coordinate mode using provider: {provider}.")
    except Exception as e:
        logger.critical(f"Failed to initialize Agno team during lifespan setup: {e}", exc_info=True)
        # Decide how to handle this - re-raise, exit, or continue without a team?
        # For now, re-raise to prevent server starting in a broken state.
        raise e

    try:
        yield
    finally:
        logger.info("Shutting down application resources...")
        app_context = None

# Initialize FastMCP
mcp = FastMCP()

# --- MCP Handlers ---

@mcp.prompt("sequential-thinking")
def sequential_thinking_prompt(problem: str, context: str = ""):
    """
    Starter prompt for sequential thinking that ENCOURAGES non-linear exploration
    using coordinate mode. Returns separate user and assistant messages.
    """
    min_thoughts = 5 # Set a reasonable minimum number of initial thoughts

    user_prompt_text = f"""Initiate a comprehensive sequential thinking process for the following problem:

Problem: {problem}
{f'Context: {context}' if context else ''}"""

    assistant_guidelines = f"""Okay, let's start the sequential thinking process. Here are the guidelines and the process we'll follow using the 'coordinate' mode team:

**Sequential Thinking Goals & Guidelines (Coordinate Mode):**

1.  **Estimate Steps:** Analyze the problem complexity. Your initial `totalThoughts` estimate should be at least {min_thoughts}.
2.  **First Thought:** Call the 'sequentialthinking' tool with `thoughtNumber: 1`, your estimated `totalThoughts` (at least {min_thoughts}), and `nextThoughtNeeded: True`. Structure your first thought as: "Plan a comprehensive analysis approach for: {problem}"
3.  **Encouraged Revision:** Actively look for opportunities to revise previous thoughts if you identify flaws, oversights, or necessary refinements based on later analysis (especially from the Coordinator synthesizing Critic/Analyzer outputs). Use `isRevision: True` and `revisesThought: <thought_number>` when performing a revision. Robust thinking often involves self-correction. Look for 'RECOMMENDATION: Revise thought #X...' in the Coordinator's response.
4.  **Encouraged Branching:** Explore alternative paths, perspectives, or solutions where appropriate. Use `branchFromThought: <thought_number>` and `branchId: <unique_branch_name>` to initiate branches. Exploring alternatives is key to thorough analysis. Consider suggestions for branching proposed by the Coordinator (e.g., 'SUGGESTION: Consider branching...').
5.  **Extension:** If the analysis requires more steps than initially estimated, use `needsMoreThoughts: True` on the thought *before* you need the extension.
6.  **Thought Content:** Each thought must:
    *   Be detailed and specific to the current stage (planning, analysis, critique, synthesis, revision, branching).
    *   Clearly explain the *reasoning* behind the thought, especially for revisions and branches.
    *   Conclude by outlining what the *next* thought needs to address to fulfill the overall plan, considering the Coordinator's synthesis and suggestions.

**Process:**

*   The `sequentialthinking` tool will track your progress. The Agno team operates in 'coordinate' mode. The Coordinator agent receives your thought, delegates sub-tasks to specialists (like Analyzer, Critic), and synthesizes their outputs, potentially including recommendations for revision or branching.
*   Focus on insightful analysis, constructive critique (leading to potential revisions), and creative exploration (leading to potential branching).
*   Actively reflect on the process. Linear thinking might be insufficient for complex problems.

Proceed with the first thought based on these guidelines."""

    return [
        {
            "description": "Starter prompt for non-linear sequential thinking (coordinate mode), providing problem and guidelines separately.",
            "messages": [
                {"role": "user", "content": {"type": "text", "text": user_prompt_text}},
                {"role": "assistant", "content": {"type": "text", "text": assistant_guidelines}}
            ]
        }
    ]


@mcp.tool()
async def sequentialthinking(thought: str, thoughtNumber: int, totalThoughts: int, nextThoughtNeeded: bool,
                      isRevision: bool = False, revisesThought: Optional[int] = None,
                      branchFromThought: Optional[int] = None, branchId: Optional[str] = None,
                      needsMoreThoughts: bool = False) -> str:
    """
    A detailed tool for dynamic and reflective problem-solving through thoughts.

    This tool helps analyze problems through a flexible thinking process that can adapt and evolve.
    Each thought can build on, question, or revise previous insights as understanding deepens.
    It uses an Agno multi-agent team (in coordinate mode) to process each thought, where a
    Coordinator delegates sub-tasks to specialists (Planner, Researcher, Analyzer, Critic, Synthesizer)
    and synthesizes their outputs.

    When to use this tool:
    - Breaking down complex problems into manageable steps.
    - Planning and design processes requiring iterative refinement and revision.
    - Complex analysis where the approach might need course correction based on findings.
    - Problems where the full scope or optimal path is not clear initially.
    - Situations requiring a multi-step solution with context maintained across steps.
    - Tasks where focusing on relevant information and filtering out noise is crucial.
    - Developing and verifying solution hypotheses through a chain of reasoning.

    Key features & usage guidelines:
    - The process is driven by the caller (e.g., an LLM) making sequential calls to this tool.
    - Start with an initial estimate for `totalThoughts`, but adjust it dynamically via subsequent calls if needed.
    - Use `isRevision=True` and `revisesThought` to explicitly revisit and correct previous steps.
    - Use `branchFromThought` and `branchId` to explore alternative paths or perspectives.
    - If the estimated `totalThoughts` is reached but more steps are needed, set `needsMoreThoughts=True` on the *last* thought within the current estimate to signal the need for extension.
    - Express uncertainty and explore alternatives within the `thought` content.
    - Generate solution hypotheses within the `thought` content when appropriate.
    - Verify hypotheses in subsequent `thought` steps based on the reasoning chain.
    - The caller should repeat the process, calling this tool for each step, until a satisfactory solution is reached.
    - Set `nextThoughtNeeded=False` only when the caller determines the process is complete and a final answer is ready.

    Parameters:
        thought (str): The content of the current thinking step. This can be an analytical step,
                       a plan, a question, a critique, a revision, a hypothesis, or verification.
                       Make it specific enough to imply the desired action.
        thoughtNumber (int): The sequence number of this thought (>=1). Can exceed initial `totalThoughts`
                             if the process is extended.
        totalThoughts (int): The current *estimate* of the total thoughts required for the process.
                             This can be adjusted by the caller in subsequent calls. Minimum 5 suggested.
        nextThoughtNeeded (bool): Indicates if the caller intends to make another call to this tool
                                  after the current one. Set to False only when the entire process is deemed complete.
        isRevision (bool, optional): True if this thought revises or corrects a previous thought. Defaults to False.
        revisesThought (int, optional): The `thoughtNumber` of the thought being revised, required if `isRevision` is True.
                                        Must be less than the current `thoughtNumber`.
        branchFromThought (int, optional): The `thoughtNumber` from which this thought branches to explore an alternative path.
                                           Defaults to None.
        branchId (str, optional): A unique identifier for the branch being explored, required if `branchFromThought` is set.
                                  Defaults to None.
        needsMoreThoughts (bool, optional): Set to True on a thought if the caller anticipates needing more
                                            steps beyond the current `totalThoughts` estimate *after* this thought.
                                            Defaults to False.

    Returns:
        str: The Coordinator agent's synthesized response based on specialist contributions for the current `thought`.
             Includes guidance for the caller on potential next steps (e.g., suggestions for revision or branching
             based on the specialists' analysis). The caller uses this response to formulate the *next* thought.
    """
    global app_context
    if not app_context or not app_context.team:
        logger.error("Application context or Agno team not initialized during tool call.")
        # Attempt re-initialization cautiously, or fail hard.
        # Let's try re-initialization if app_lifespan wasn't used or failed silently.
        logger.warning("Attempting to re-initialize team due to missing context...")
        try:
             team = create_sequential_thinking_team()
             app_context = AppContext(team=team) # Re-create context
             logger.info("Successfully re-initialized team and context.")
        except Exception as init_err:
             logger.critical(f"Failed to re-initialize Agno team during tool call: {init_err}", exc_info=True)
             # Return only the error message string
             return f"Critical Error: Application context not available and re-initialization failed: {init_err}"
             # Or raise Exception("Critical Error: Application context not available.")

    MIN_TOTAL_THOUGHTS = 5 # Keep a minimum suggestion

    try:
        # --- Initial Validation and Adjustments ---
        adjusted_total_thoughts = max(MIN_TOTAL_THOUGHTS, totalThoughts)
        if adjusted_total_thoughts != totalThoughts:
            logger.info(f"Initial totalThoughts ({totalThoughts}) is below suggested minimum {MIN_TOTAL_THOUGHTS}. Proceeding, but consider if more steps might be needed.")
            # Let the LLM manage the estimate.

        adjusted_next_thought_needed = nextThoughtNeeded
        if thoughtNumber >= totalThoughts and not needsMoreThoughts:
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

        # --- Logging and History Update ---
        log_prefix = "--- Received Thought ---"
        if current_input_thought.isRevision:
            log_prefix = f"--- Received REVISION Thought (revising #{current_input_thought.revisesThought}) ---"
        elif current_input_thought.branchFromThought is not None:
            log_prefix = f"--- Received BRANCH Thought (from #{current_input_thought.branchFromThought}, ID: {current_input_thought.branchId}) ---"

        formatted_log_thought = format_thought_for_log(current_input_thought)
        logger.info(f"\n{log_prefix}\n{formatted_log_thought}\n")

        # Add the thought to history
        app_context.add_thought(current_input_thought)

        # --- Process Thought with Team (Coordinate Mode) ---
        logger.info(f"Passing thought #{thoughtNumber} to the Coordinator...")

        # Prepare input for the team coordinator. Pass the core thought content.
        # Include context about revision/branching directly in the input string for the coordinator.
        input_prompt = f"Process Thought #{current_input_thought.thoughtNumber}:\n"
        if current_input_thought.isRevision and current_input_thought.revisesThought is not None:
             # Find the original thought text
             original_thought_text = "Unknown Original Thought"
             for hist_thought in app_context.thought_history[:-1]: # Exclude current one
                 if hist_thought.thoughtNumber == current_input_thought.revisesThought:
                     original_thought_text = hist_thought.thought
                     break
             input_prompt += f"**This is a REVISION of Thought #{current_input_thought.revisesThought}** (Original: \"{original_thought_text}\").\n"
        elif current_input_thought.branchFromThought is not None and current_input_thought.branchId is not None:
             # Find the branching point thought text
             branch_point_text = "Unknown Branch Point"
             for hist_thought in app_context.thought_history[:-1]:
                 if hist_thought.thoughtNumber == current_input_thought.branchFromThought:
                     branch_point_text = hist_thought.thought
                     break
             input_prompt += f"**This is a BRANCH (ID: {current_input_thought.branchId}) from Thought #{current_input_thought.branchFromThought}** (Origin: \"{branch_point_text}\").\n"

        input_prompt += f"\nThought Content: \"{current_input_thought.thought}\""

        # Call the team's arun method. The coordinator agent will handle it.
        team_response = await app_context.team.arun(input_prompt)

        # Ensure coordinator_response is a string, default to empty string if None
        coordinator_response_content = team_response.content if hasattr(team_response, 'content') else None
        coordinator_response = str(coordinator_response_content) if coordinator_response_content is not None else ""

        logger.info(f"Coordinator finished processing thought #{thoughtNumber}.")
        logger.debug(f"Coordinator Raw Response:\n{coordinator_response}")


        # --- Guidance for Next Step (Coordinate Mode) ---
        additional_guidance = "\n\nGuidance for next step:" # Initialize

        if not current_input_thought.nextThoughtNeeded:
            # Keep the message for the final thought concise
            additional_guidance = "\n\nThis is the final thought. Review the Coordinator's final synthesis."
        else:
            # Start guidance text for non-final thoughts
            additional_guidance += "\n- **Revision/Branching:** Look for 'RECOMMENDATION: Revise thought #X...' or 'SUGGESTION: Consider branching...' in the response."
            additional_guidance += " Use `isRevision=True`/`revisesThought=X` for revisions or `branchFromThought=Y`/`branchId='...'` for branching accordingly."
            additional_guidance += "\n- **Next Thought:** Based on the Coordinator's response, formulate the next logical thought, addressing any points raised."


        # --- Build Result ---
        result_data = {
            "processedThoughtNumber": current_input_thought.thoughtNumber,
            "estimatedTotalThoughts": current_input_thought.totalThoughts,
            "nextThoughtNeeded": current_input_thought.nextThoughtNeeded,
            # Ensure both parts are strings before concatenating
            "coordinatorResponse": coordinator_response + str(additional_guidance),
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

        # Return only the coordinatorResponse string
        return result_data["coordinatorResponse"]

    except ValidationError as e:
        logger.error(f"Validation Error processing tool call: {e}")
        # Return only the error message string
        return f"Input validation failed: {e}"
    except Exception as e:
        logger.exception(f"Error processing tool call") # Log full traceback
        # Return only the error message string
        return f"An unexpected error occurred: {str(e)}"

# --- Main Execution ---

def run():
    """Initializes and runs the MCP server in coordinate mode."""
    selected_provider = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    logger.info(f"Using provider: {selected_provider}")
    logger.info(f"Initializing Sequential Thinking Server (Coordinate Mode) with Provider: {selected_provider}...")

    global app_context
    # Initialize application resources using the lifespan manager implicitly if running via framework
    # For direct script execution, we initialize here.
    # If using app_lifespan, this manual init might be redundant depending on framework.
    if not app_context: # Check if context already exists (e.g., from lifespan manager)
        logger.info("Initializing application resources directly (Coordinate Mode)...")
        try:
             team = create_sequential_thinking_team()
             app_context = AppContext(team=team)
             logger.info(f"Agno team initialized directly in coordinate mode using provider: {selected_provider}.")
        except Exception as e:
             logger.critical(f"Failed to initialize Agno team: {e}", exc_info=True)
             sys.exit(1)


    try:
        logger.info("Sequential Thinking MCP Server running on stdio (Coordinate Mode)")
        if not app_context:
            logger.critical("FATAL: Application context not initialized before run.")
            sys.exit(1)

        mcp.run(transport="stdio")
    finally:
        logger.info("Shutting down application resources...")
        app_context = None # Clean up context if initialized directly

def check_environment_variables():
    """Checks for necessary environment variables based on the selected provider."""
    provider = os.environ.get("LLM_PROVIDER", "deepseek").lower()
    api_key_var = ""
    base_url_var = "" # Some providers might not strictly need a base URL override

    if provider == "deepseek":
        api_key_var = "DEEPSEEK_API_KEY"
    elif provider == "groq":
        api_key_var = "GROQ_API_KEY"
    elif provider == "openrouter":
        api_key_var = "OPENROUTER_API_KEY"
    if api_key_var and api_key_var not in os.environ:
        logger.warning(f"{api_key_var} environment variable not found. Model initialization for '{provider}' might fail.")
    try:
        ModelClass, _, _ = get_model_config() # Just need the class for dummy init
        dummy_model = ModelClass(id="dummy-check") # Use a placeholder ID
        researcher_for_check = Agent(name="CheckAgent", tools=[ExaTools()], model=dummy_model)
        uses_exa = any(isinstance(t, ExaTools) for t in researcher_for_check.tools)

        if uses_exa and "EXA_API_KEY" not in os.environ:
             logger.warning("EXA_API_KEY environment variable not found, but ExaTools are configured in a team member. Researcher agent might fail.")
    except Exception as e:
        logger.error(f"Could not perform ExaTools check due to an error: {e}")


if __name__ == "__main__":
    check_environment_variables()
    try:
        run()
    except Exception as e:
        logger.critical(f"Failed during server run: {e}", exc_info=True)
        sys.exit(1)
        
