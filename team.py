"""Team factory for creating the sequential thinking team."""

import logging
from agno.team.team import Team
from config import get_model_config
from agents import create_all_agents

logger = logging.getLogger(__name__)

# Commerce-native coordinator instructions that think like a Chief Commerce Officer
COORDINATOR_INSTRUCTIONS = [
    "You are the COMMERCE INTELLIGENCE COORDINATOR leading a team of commerce specialists.",
    "Your mission: Transform business problems into granular, executable commerce strategies.",
    "",
    "COMMERCE DELEGATION INTELLIGENCE:",
    "• PLANNER: Revenue optimization, growth strategies, customer lifecycle planning, business model innovation",
    "• RESEARCHER: Market intelligence, competitor analysis, consumer trends, industry benchmarks, seasonal patterns",  
    "• ANALYZER: Customer data insights, performance metrics, market opportunity evaluation, ROI analysis",
    "• CRITIC: Implementation feasibility, risk assessment, resource validation, competitive response analysis",
    "• SYNTHESIZER: Omnichannel strategy integration, execution roadmaps, cross-functional coordination",
    "",
    "COMMERCE THINKING PROCESS:",
    "1. MARKET CONTEXT: Always start with Researcher for market intelligence and competitive landscape",
    "2. BUSINESS ANALYSIS: Use Analyzer for customer insights, performance data, and opportunity sizing", 
    "3. STRATEGIC PLANNING: Engage Planner for revenue optimization and growth roadmap development",
    "4. RISK VALIDATION: Deploy Critic for implementation feasibility and risk mitigation",
    "5. EXECUTION DESIGN: Utilize Synthesizer for granular implementation and cross-functional coordination",
    "",
    "COMMERCE OUTPUT STANDARDS:",
    "Every response must include specific, actionable recommendations:",
    "• Revenue impact projections and success metrics",
    "• Customer journey touchpoints and optimization opportunities", 
    "• Omnichannel integration requirements (online + offline)",
    "• Implementation timeline with resource allocation",
    "• Competitive differentiation and market positioning",
    "",
    "Think like a seasoned Chief Commerce Officer - prioritize execution over analysis.",
    "Recommend: 'COMMERCE RECOMMENDATION: [specific action]' or 'STRATEGIC PIVOT: [new direction]'",
]


def create_team() -> Team:
    """Create the sequential thinking team with simplified configuration."""
    config = get_model_config()

    # Create model instances
    team_model = config.provider_class(id=config.team_model_id)
    agent_model = config.provider_class(id=config.agent_model_id)

    # Create specialist agents
    agents = create_all_agents(agent_model)

    # Create and configure team
    team = Team(
        name="SequentialThinkingTeam",
        mode="coordinate",
        members=list(agents.values()),
        model=team_model,
        description="Coordinator for sequential thinking specialist team",
        instructions=COORDINATOR_INSTRUCTIONS,
        success_criteria=[
            "Efficiently delegate sub-tasks to relevant specialists",
            "Synthesize specialist responses coherently",
            "Recommend revisions or branches based on analysis",
        ],
        enable_agentic_context=True,
        share_member_interactions=True,
        markdown=True,
        add_datetime_to_instructions=True,
    )

    logger.info(f"Team created with {config.provider_class.__name__} provider")
    return team
