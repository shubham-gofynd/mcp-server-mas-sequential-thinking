# Sequential Thinking Multi-Agent System (MAS)

A FastMCP-based Multi-Agent System implementing sequential thinking through coordinated specialized agents. This system leverages the power of multiple intelligent agents working in concert to break down complex problems and process them through structured thinking steps.

## Overview

The server provides a sophisticated sequential thinking tool powered by a true Multi-Agent System (MAS) architecture:
- Processes complex problems through coordinated multi-agent analysis with specialized roles
- Maintains structured thought chains with support for revisions and branches
- Integrates with external knowledge sources through the Researcher agent
- Provides detailed logging for process tracking and debugging
- Delivers higher quality analysis than single-agent approaches through specialized expertise

> **Token Consumption Warning**: Due to the Multi-Agent System architecture, this tool consumes significantly more tokens than single-agent alternatives. Each thought invokes multiple specialized agents working in parallel, resulting in 3-5x higher token usage compared to traditional approaches. Consider this when planning usage and budgeting.

## Core Components

### Multi-Agent System Architecture

The system implements a true Multi-Agent System with specialized agents, each having distinct expertise:

1. **Team Coordinator**
   - Orchestrates the entire thinking process
   - Breaks down tasks into subtasks
   - Explicitly delegates work to specialized agents
   - Synthesizes team outputs into coherent responses
   - Maintains quality and logical progression

2. **Strategic Planner**
   - Develops strategic approaches
   - Evaluates steps and their implications
   - Considers timeline and resource impacts

3. **Researcher**
   - Gathers information using Exa search tools
   - Validates data from external sources
   - Synthesizes findings into actionable insights

4. **Core Analyzer**
   - Performs deep analysis
   - Identifies patterns and relationships
   - Generates insights and implications

5. **Quality Controller (Critic)**
   - Evaluates logical consistency
   - Identifies potential biases and gaps
   - Suggests specific improvements

6. **Integration Specialist (Synthesizer)**
   - Combines insights from multiple sources
   - Forms coherent conclusions
   - Structures information clearly

### Coordination Architecture

The system implements Agno's **Coordinate Mode** architecture:

1. **Task Receipt & Analysis**
   - Coordinator receives the thought input
   - Analyzes thought content and context
   - Determines required expertise

2. **Task Decomposition**
   - Breaks thought into specialized subtasks
   - Maps subtasks to team member expertise
   - Creates explicit delegation plan

3. **Parallel Processing**
   - Team members work on assigned subtasks
   - Each member applies specialized expertise
   - Processing occurs in parallel when possible

4. **Output Synthesis**
   - Coordinator collects all team members' outputs
   - Synthesizes into coherent, structured response
   - Ensures logical flow and comprehensive coverage

5. **Quality Assurance**
   - Evaluates against success criteria
   - Ensures all aspects of thought addressed
   - Maintains consistency across thought chain

This coordination architecture ensures optimal utilization of specialized agent capabilities while maintaining coherent output structure and logical progression.

## Requirements

- Python 3.10 or higher
- DeepSeek API key
- Exa API key (for research capabilities)
- uv package manager (recommended for dependency management)

## Environment Setup

1. Set required environment variables:
```bash
export DEEPSEEK_API_KEY="your_key_here"
export DEEPSEEK_BASE_URL="your_url_here"
export EXA_API_KEY="your_key_here"  # Required for research capabilities
```

2. Install dependencies using uv (recommended for faster installation):
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv pip install -e .
```

Alternatively, use pip:
```bash
pip install -e .
```

## Token Consumption Considerations

This Multi-Agent System is designed for depth of analysis rather than efficiency of token usage. Here are important considerations:

1. **High Token Consumption**
   - Each thought step activates 5-6 specialized agents
   - Coordinator agent performs additional processing for task delegation and synthesis
   - Complete analysis can consume 3-5x more tokens than single-agent alternatives

2. **Scaling Considerations**
   - Token usage scales linearly with complexity of thoughts
   - Lengthier inputs result in proportionally higher token usage
   - Each agent receives context from the coordinator, multiplying context costs

3. **Optimization Strategies**
   - Use concise, focused thought descriptions
   - Consider limiting total number of thoughts for simpler problems
   - Break extremely complex problems into separate sequential thinking chains
   - Monitor token usage through logging to identify optimization opportunities

4. **When to Use**
   - Complex problems requiring multi-disciplinary expertise
   - Critical analyses where depth and quality outweigh token costs
   - Scenarios benefiting from diverse perspectives and specialized knowledge

## Usage

The server exposes the `sequentialthinking` tool through MCP, which processes thoughts with the following parameters:

```python
{
    "thought": str,              # The current thinking step
    "thoughtNumber": int,        # Current sequence number (≥1)
    "totalThoughts": int,        # Estimated total thoughts needed (≥5)
    "nextThoughtNeeded": bool,   # Whether another thought step is needed
    "isRevision": bool,          # Optional: Whether this revises previous thinking
    "revisesThought": int,       # Optional: Which thought is being reconsidered
    "branchFromThought": int,    # Optional: Branch point thought number
    "branchId": str,             # Optional: Branch identifier
    "needsMoreThoughts": bool    # Optional: If more thoughts needed beyond estimate
}
```

### Enhanced Features

The system includes several advanced features to ensure comprehensive analysis:

1. **Minimum Analysis Depth**
   - Automatically enforces a minimum of 5 thinking steps
   - Adjusts totalThoughts parameter if set below the minimum
   - Ensures sufficient depth for multi-agent analysis

2. **Automatic Step Guidance**
   - Provides contextual guidance for next steps based on current position
   - Suggests appropriate focus areas as the analysis progresses
   - Helps maintain logical progression through the thinking process

3. **Flexible Step Planning**
   - Adapts to problem complexity without enforcing rigid structures
   - Allows external LLMs to determine appropriate step count (minimum 5)
   - Maintains balance between structure and flexibility

4. **Smart Parameter Validation**
   - Validates and adjusts nextThoughtNeeded for logical consistency
   - Ensures proper sequencing of thought numbers
   - Maintains thought chain integrity

### Example Usage

```python
from mcp.client import MCPClient

client = MCPClient()

# Example of an initial step with flexible approach
response = await client.call_tool("sequentialthinking", {
    "thought": """Plan a comprehensive analysis approach for solving this problem.
    Objectives for team members:
    - Strategic Planner: Develop a framework for analyzing the core components
    - Researcher: Identify key information needs and potential data sources
    - Analyzer: Establish metrics and analysis methodology
    - Critic: Define success criteria and potential failure points
    - Synthesizer: Create structure for integrating diverse perspectives""",
    "thoughtNumber": 1,
    "totalThoughts": 5,  # Minimum required steps
    "nextThoughtNeeded": True
})

# Example of a revision step
response = await client.call_tool("sequentialthinking", {
    "thought": "Revisit and deepen the analysis of critical components, focusing on edge cases and potential failure modes",
    "thoughtNumber": 3,
    "totalThoughts": 5,
    "nextThoughtNeeded": True,
    "isRevision": True,
    "revisesThought": 2
})

# Example of a parallel analysis branch
response = await client.call_tool("sequentialthinking", {
    "thought": "Explore alternative approaches based on the evaluation results",
    "thoughtNumber": 4,
    "totalThoughts": 5,
    "nextThoughtNeeded": True,
    "branchFromThought": 2,
    "branchId": "alternative_analysis"
})
```

### Recommended Analysis Process

The server supports a flexible multi-step analysis process with a minimum of 5 steps:

1. **Initial Planning** (Typically Step 1)
   - Problem decomposition
   - Analysis framework setup
   - Team member engagement planning

2. **Research Phase** (Typically Step 2)
   - Information gathering
   - Data validation
   - Context establishment

3. **Deep Analysis** (Typically Step 3)
   - Pattern identification
   - Relationship mapping
   - Core insight generation

4. **Evaluation and Synthesis** (Typically Step 4)
   - Multi-perspective assessment
   - Integration of findings
   - Framework development

5. **Conclusions and Recommendations** (Typically Step 5)
   - Action item development
   - Key insight compilation
   - Next steps outline

Additional steps can be added for complex problems requiring deeper analysis. The system also supports revision steps and parallel analysis branches for comprehensive exploration.

## Logging

The server implements comprehensive logging with both file and console handlers:
- Log files are stored in `~/.sequential_thinking/logs`
- Rotating file handler with 10MB max size and 5 backups
- Console output for INFO level and above
- Detailed formatting with timestamps and log levels

## Development

For development work:
1. Clone the repository
2. Install development dependencies using uv (recommended):
```bash
uv pip install -e ".[dev]"
```
Or with pip:
```bash
pip install -e ".[dev]"
```
3. Ensure environment variables are set
4. Run the server:
```bash
python main.py
```

## Error Handling

The server includes robust error handling for:
- Input validation through Pydantic models
- API key verification
- Agent initialization failures
- Tool execution errors

## License

[License information here]

This project uses:
- DeepSeek Chat API for agent intelligence
- Exa API for research capabilities
- FastMCP for server implementation
- Agno framework for multi-agent coordination
- uv package manager for dependency management
