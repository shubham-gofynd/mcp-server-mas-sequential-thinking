"""Simplified agent factory using composition and capability patterns (Agno 1.8.1)."""

from dataclasses import dataclass
from typing import Any, Dict, List
from agno.agent import Agent
from agno.models.base import Model
from agno.tools.reasoning import ReasoningTools
from agno.tools.exa import ExaTools


TOOL_CALL_CONTRACT = [
    "TOOL-CALL CONTRACT (MANDATORY):",
    "- Output ONLY a single JSON OBJECT for tool arguments (no arrays/strings/markdown).",
    "- ReasoningTools.think: {\"title\": string, \"thought\": string}.",
    "- ReasoningTools.analyze: {\"title\": string, \"result\": string, \"analysis\": string}.",
    "- ExaTools.*: always pass an OBJECT (e.g., {\"query\": \"...\", \"num_results\": 5}).",
    "- Do NOT add extra keys (e.g., 'confidence') or dotted keys.",
]


@dataclass(frozen=True)
class AgentCapability:
    """Defines agent capabilities and configuration (stores tool INSTANCES)."""

    role: str
    description: str
    tools: List[Any]          # instances (e.g., ReasoningTools(...), ExaTools(...))
    role_description: str

    def get_instructions(self) -> List[str]:
        """Generate instructions for this capability."""
        return [
            "You are a specialist agent receiving specific sub-tasks from the Team Coordinator.",
            f"Your role: {self.role_description}",
            "For each sub-task, ALWAYS follow: 1) ReasoningTools.think → 2) Tool call (if needed) → 3) ReasoningTools.analyze.",
            "Process: 1) Understand the delegated sub-task, 2) Use tools as needed, 3) Provide focused results, 4) Return response to Coordinator.",
            "Focus on accuracy and relevance for your assigned task.",
            "Only call tools that appear in tools/list. Never invent tool names.",
            "When calling a tool, output only a JSON object containing the tool's arguments (no extra prose).",
        ] + TOOL_CALL_CONTRACT

    def create_tools(self) -> List[Any]:
        """Return the pre-instantiated tool instances."""
        return self.tools


class AgentFactory:
    """Factory for creating specialized agents with capability composition."""

    # Core capabilities registry (per-role tool instances)
    CAPABILITIES = {
        "planner": AgentCapability(
            role="Strategic Commerce Planner",
            description="Develops strategic commerce plans and revenue optimization roadmaps based on delegated sub-tasks",
            tools=[
                # Lean: structured planning via think; analyze off to keep runs fast
                ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True),
            ],
            role_description="Commerce Strategy Expert: Develop revenue optimization strategies, customer lifecycle planning, seasonal campaign roadmaps, omnichannel growth strategies, and business model innovation. Focus on measurable outcomes, competitive differentiation, and scalable execution frameworks.",
        ),
        "researcher": AgentCapability(
            role="Commerce Intelligence Researcher",
            description=("Gathers and validates commerce-specific information based on delegated research sub-tasks."
            "You have access to ExaTools for web research. "
            "Use the following tool functions when relevant:\n"
            "- search_exa(query: str, num_results: int = 5, category: Optional[str]) → run a web search and return JSON results.\n"
            "- get_contents(urls: list[str]) → fetch full content for given URLs.\n"
            "- find_similar(url: str, num_results: int = 5) → discover pages similar to a given URL.\n"
            "- exa_answer(query: str, text: bool = False) → generate an answer with citations based on Exa search results.\n"
            "- research(instructions: str, output_schema: Optional[dict]) → create and poll a deeper research task.\n"
            "Always call these tools with valid JSON arguments (no free-text). "
            "If a required argument is missing, ask for clarification rather than inventing values. "
            "Do not invent new tool names — only use the ones listed above."),
            tools=[
                # Light reasoning helps shape queries
                ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True),
                # Full Exa capability (search_exa, get_contents, find_similar, exa_answer)
                ExaTools(api_key="15b567d1-9af3-4ae3-bd49-e5d5bee228b6"),
            ],
            role_description="Market Intelligence Specialist: Research consumer behavior trends, competitive strategies, seasonal market dynamics, industry benchmarks, emerging commerce technologies, and customer sentiment analysis. Provide actionable market intelligence for strategic decision-making.",
        ),
        "analyzer": AgentCapability(
            role="Commerce Data Analyst",
            description="Performs commerce-focused analysis based on delegated analytical sub-tasks",
            tools=[
                # Full reasoning where depth matters
                ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True),
            ],
            role_description="Business Intelligence Expert: Analyze customer data patterns, revenue performance metrics, market opportunity sizing, competitive positioning, campaign effectiveness, and ROI optimization. Generate data-driven insights for strategic commerce decisions.",
        ),
        "critic": AgentCapability(
            role="Commerce Risk Assessor",
            description="Critically evaluates commerce strategies and implementation feasibility based on delegated critique sub-tasks",
            tools=[
                # Full reasoning for critique (you can set analyze=False if you prefer)
                ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True),
            ],
            role_description="Implementation Feasibility Expert: Evaluate strategic assumptions, assess implementation risks, validate resource requirements, analyze competitive response scenarios, and provide constructive critique for commerce strategy optimization and execution success.",
        ),
        "synthesizer": AgentCapability(
            role="Commerce Strategy Integrator",
            description="Integrates commerce insights and creates comprehensive execution plans based on delegated synthesis sub-tasks",
            tools=[
                # Lean synthesis via think; analyze off to keep runs short
                ReasoningTools(think=True, analyze=True, add_instructions=True, add_few_shot=True),
            ],
            role_description="Execution Strategy Expert: Integrate market intelligence into comprehensive omnichannel strategies, create granular implementation roadmaps, design cross-functional coordination plans, and synthesize actionable commerce recommendations with measurable success criteria.",
        ),
    }

    @classmethod
    def create_agent(cls, agent_type: str, model: Model, **kwargs) -> Agent:
        """Create a specialized agent using capability composition."""
        if agent_type not in cls.CAPABILITIES:
            raise ValueError(
                f"Unknown agent type: {agent_type}. Available: {list(cls.CAPABILITIES.keys())}"
            )

        capability = cls.CAPABILITIES[agent_type]
        instructions = capability.get_instructions()

        # Add any additional instructions
        extra = kwargs.pop("extra_instructions", None)
        if extra:
            instructions.extend(extra)

        return Agent(
            name=agent_type.title(),
            role=capability.role,
            description=capability.description,
            tools=capability.create_tools(),   # instances, ready to register
            instructions=instructions,
            model=model,
            add_datetime_to_instructions=True,
            markdown=True,
            **kwargs,
        )

    @classmethod
    def create_all_agents(cls, model: Model) -> Dict[str, Agent]:
        """Create all specialist agents using factory pattern."""
        return {agent_type: cls.create_agent(agent_type, model) for agent_type in cls.CAPABILITIES.keys()}


# Convenience functions for backward compatibility
def create_agent(agent_type: str, model: Model, **kwargs) -> Agent:
    return AgentFactory.create_agent(agent_type, model, **kwargs)


def create_all_agents(model: Model) -> Dict[str, Agent]:
    return AgentFactory.create_all_agents(model)
