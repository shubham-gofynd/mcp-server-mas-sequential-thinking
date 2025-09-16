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
        """Extract key insights from previous thoughts for context"""
        if current_thought_number <= 1:
            return ""
        
        previous_thoughts = self.thought_history[:current_thought_number-1]
        if not previous_thoughts:
            return ""
        
        # Extract key insights from existing thought history
        insights = []
        decisions = []
        
        for thought in previous_thoughts:
            thought_content = thought.thought.lower()
            
            # Simple pattern extraction for context building
            if any(word in thought_content for word in ["recommend", "suggest", "should"]):
                decisions.append(f"T{thought.thought_number}: {thought.thought[:80]}...")
            elif any(word in thought_content for word in ["found", "discovered", "identified"]):
                insights.append(f"T{thought.thought_number}: {thought.thought[:80]}...")
        
        context_parts = []
        if insights:
            context_parts.append(f"Key Insights: {'; '.join(insights[:2])}")
        if decisions:
            context_parts.append(f"Decisions Made: {'; '.join(decisions[:2])}")
        
        return " | ".join(context_parts) if context_parts else ""
