"""Session management for thought history and branching."""

from dataclasses import dataclass, field
from typing import Dict, List
from agno.team.team import Team
from models import ThoughtData


@dataclass
class SessionMemory:
    """Manages thought history and branches for a session."""

    team: Team
    thought_history: List[ThoughtData] = field(default_factory=list)
    branches: Dict[str, List[ThoughtData]] = field(default_factory=dict)

    def add_thought(self, thought: ThoughtData) -> None:
        """Add a thought to history and manage branches."""
        self.thought_history.append(thought)

        # Handle branching
        if thought.branch_from is not None and thought.branch_id is not None:
            if thought.branch_id not in self.branches:
                self.branches[thought.branch_id] = []
            self.branches[thought.branch_id].append(thought)

    def find_thought_content(self, thought_number: int) -> str:
        """Find the content of a specific thought by number."""
        for thought in self.thought_history:
            if thought.thought_number == thought_number:
                return thought.thought
        return "Unknown thought"

    def get_branch_summary(self) -> Dict[str, int]:
        """Get summary of all branches."""
        return {
            branch_id: len(thoughts) for branch_id, thoughts in self.branches.items()
        }

    def get_current_branch_id(self, thought: ThoughtData) -> str:
        """Get the current branch ID for a thought."""
        return thought.branch_id if thought.branch_from is not None else "main"

    def get_contextual_insights(self, current_thought_number: int) -> str:
        """Extract commerce-focused insights from previous thoughts for accelerated context"""
        if current_thought_number <= 1:
            return ""
        
        previous_thoughts = self.thought_history[:current_thought_number-1]
        if not previous_thoughts:
            return ""
        
        # Commerce-specific insight extraction patterns
        market_insights = []
        revenue_insights = []
        customer_insights = []
        strategic_decisions = []
        
        for thought in previous_thoughts:
            thought_content = thought.thought.lower()
            
            # Market & Competitive Intelligence
            if any(word in thought_content for word in ["market", "competitor", "trend", "industry", "seasonal"]):
                market_insights.append(f"T{thought.thought_number}: {thought.thought[:100]}...")
            
            # Revenue & Performance Insights  
            elif any(word in thought_content for word in ["revenue", "profit", "roi", "conversion", "sales", "growth"]):
                revenue_insights.append(f"T{thought.thought_number}: {thought.thought[:100]}...")
            
            # Customer & Journey Insights
            elif any(word in thought_content for word in ["customer", "persona", "journey", "behavior", "segment"]):
                customer_insights.append(f"T{thought.thought_number}: {thought.thought[:100]}...")
            
            # Strategic Decisions & Recommendations
            elif any(word in thought_content for word in ["recommend", "strategy", "implement", "execute", "optimize"]):
                strategic_decisions.append(f"T{thought.thought_number}: {thought.thought[:100]}...")
        
        # Build commerce-focused context
        context_parts = []
        if market_insights:
            context_parts.append(f"Market Intelligence: {'; '.join(market_insights[:2])}")
        if revenue_insights:
            context_parts.append(f"Revenue Insights: {'; '.join(revenue_insights[:2])}")
        if customer_insights:
            context_parts.append(f"Customer Intelligence: {'; '.join(customer_insights[:2])}")
        if strategic_decisions:
            context_parts.append(f"Strategic Decisions: {'; '.join(strategic_decisions[:2])}")
        
        return " | ".join(context_parts) if context_parts else ""
