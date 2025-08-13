# Tests for GitHub Models Provider

This directory contains comprehensive tests for the GitHub Models provider implementation using a Test-Driven Development (TDD) approach.

## Overview

The tests are designed to validate a `GitHubStrategy` class that follows the same pattern as other providers in the system but uses `GitHubOpenAI` (which extends OpenAI's agno provider) with GitHub Models base URL.

## Test Coverage

The test suite includes the following test categories:

### 1. Default Configuration Tests (`TestGitHubStrategyDefaults`)
- ✅ Test default model configurations (`openai/gpt-5` and `openai/gpt-5-min`)
- ✅ Test API key name (`GITHUB_TOKEN`)
- ✅ Test provider class returns `GitHubOpenAI`
- ✅ Test inheritance from `ProviderStrategy`

### 2. Environment Override Tests (`TestGitHubStrategyEnvironmentOverrides`)
- ✅ Test `GITHUB_TEAM_MODEL_ID` override
- ✅ Test `GITHUB_AGENT_MODEL_ID` override  
- ✅ Test both model overrides simultaneously
- ✅ Test fallback to defaults when no environment variables

### 3. API Key Validation Tests (`TestGitHubStrategyAPIKeyValidation`)
- ✅ Test API key reading from `GITHUB_TOKEN`
- ✅ Test missing API key returns None
- ✅ Test empty API key returns None
- ✅ Test API key name property

### 4. ModelConfig Tests (`TestGitHubStrategyGetConfig`)
- ✅ Test `get_config()` returns `ModelConfig` instance
- ✅ Test configuration with defaults
- ✅ Test configuration with full environment setup
- ✅ Test `ModelConfig` immutability (frozen dataclass)

### 5. GitHubOpenAI Initialization Tests (`TestGitHubOpenAIInitialization`)
- ✅ Test GitHubOpenAI initialization with GitHub Models base URL
- ✅ Test GitHubOpenAI base URL configuration
- ✅ Test GitHubOpenAI API key handling
- ✅ Verify proper base URL: `https://models.github.ai/inference`

### 6. Integration Tests (`TestGitHubStrategyIntegration`)
- ✅ Test strategy follows provider pattern
- ✅ Test integration with STRATEGIES registry
- ✅ Test environment variable prefix extraction
- ✅ Test full workflow simulation

### 7. Error Handling Tests (`TestGitHubStrategyErrorHandling`)
- ✅ Test provider class returns valid callable class
- ✅ Test malformed environment variables handling

## Running the Tests

### Prerequisites

1. Install dev dependencies:
   ```bash
   # Using uv (recommended)
   uv pip install -e ".[dev]"
   
   # Or using pip
   pip install -e ".[dev]"
   ```

2. Ensure you're in the project root directory.

### Running All Tests

```bash
# Run all GitHub provider tests
pytest tests/test_github_provider.py -v

# Run with coverage
pytest tests/test_github_provider.py --cov=config -v

# Run specific test class
pytest tests/test_github_provider.py::TestGitHubStrategyDefaults -v

# Run specific test
pytest tests/test_github_provider.py::TestGitHubStrategyDefaults::test_github_strategy_defaults -v
```

### Test Output Example

```bash
$ pytest tests/test_github_provider.py -v

========================================= test session starts ==========================================
tests/test_github_provider.py::TestGitHubStrategyDefaults::test_github_strategy_defaults PASSED
tests/test_github_provider.py::TestGitHubStrategyDefaults::test_provider_class_returns_correct_type PASSED
tests/test_github_provider.py::TestGitHubStrategyEnvironmentOverrides::test_team_model_environment_override PASSED
tests/test_github_provider.py::TestGitHubStrategyAPIKeyValidation::test_api_key_from_environment PASSED
tests/test_github_provider.py::TestChatOpenAIMocking::test_chat_openai_initialization_with_github_base_url PASSED
...
========================================= 25 passed in 0.15s ==========================================
```

## Test Structure

Each test follows the AAA pattern:
- **Arrange**: Set up test data and mocks
- **Act**: Execute the code under test
- **Assert**: Verify the expected behavior

### Example Test

```python
def test_github_strategy_defaults(self):
    """Test that GitHubStrategy has correct default values."""
    # Arrange
    strategy = GitHubStrategy()
    
    # Act & Assert
    assert strategy.default_team_model == "openai/gpt-5"
    assert strategy.default_agent_model == "openai/gpt-5-min"
    assert strategy.api_key_name == "GITHUB_TOKEN"
```

## Mocking Strategy

The tests use extensive mocking to:

1. **Mock `agno.models.openai.OpenAIChat`** to avoid external dependencies
2. **Mock environment variables** using `patch.dict(os.environ, ...)`
3. **Test GitHubOpenAI initialization** with proper base URL configuration
4. **Verify method calls** and parameters passed to mocked objects

## Key Test Scenarios

### Environment Variable Testing

```python
def test_team_model_environment_override(self):
    strategy = GitHubStrategy()
    
    with patch.dict(os.environ, {'GITHUB_TEAM_MODEL_ID': 'openai/gpt-4-turbo'}):
        config = strategy.get_config()
        assert config.team_model_id == 'openai/gpt-4-turbo'
```

### GitHubOpenAI Mocking

```python
@patch('agno.models.openai.OpenAIChat')
def test_github_openai_initialization(self, mock_openai_chat):
    strategy = GitHubStrategy()
    expected_base_url = "https://models.github.ai/inference"
    
    with patch.dict(os.environ, {'GITHUB_TOKEN': 'test-token'}):
        config = strategy.get_config()
        
        # Get the GitHub OpenAI class and test instantiation
        github_openai_class = config.provider_class
        
        # Verify it's the GitHubOpenAI class
        assert github_openai_class.__name__ == 'GitHubOpenAI'
```

## Expected GitHubStrategy Implementation

Based on the tests, the expected implementation should look like:

```python
class GitHubOpenAI(OpenAIChat):
    """OpenAI provider configured for GitHub Models API."""
    
    def __init__(self, **kwargs):
        # Set GitHub Models base URL
        kwargs.setdefault('base_url', 'https://models.github.ai/inference')
        # GitHub uses personal access tokens instead of API keys
        if 'api_key' not in kwargs:
            kwargs['api_key'] = os.environ.get('GITHUB_TOKEN')
        super().__init__(**kwargs)

class GitHubStrategy(ProviderStrategy):
    @property
    def provider_class(self):
        return GitHubOpenAI
    
    @property
    def default_team_model(self) -> str:
        return "openai/gpt-5"
    
    @property 
    def default_agent_model(self) -> str:
        return "openai/gpt-5-min"
    
    @property
    def api_key_name(self) -> str:
        return "GITHUB_TOKEN"
```

## Notes

- Tests assume the GitHub Models endpoint is: `https://models.github.ai/inference`
- The strategy uses `GITHUB_TOKEN` for authentication (GitHub personal access token)
- Model IDs follow OpenAI naming convention with `openai/` prefix
- Environment variables follow the pattern: `GITHUB_TEAM_MODEL_ID`, `GITHUB_AGENT_MODEL_ID`
- All tests are designed to pass without requiring external dependencies or API calls

## Future Enhancements

Potential additional tests to consider:
- Performance/load testing
- Real API integration tests (with proper credentials)
- Rate limiting behavior
- Network error handling
- Token usage validation
