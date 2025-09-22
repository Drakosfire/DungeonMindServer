# StatBlock Generator Test Suite

This directory contains a comprehensive test suite for the StatBlock Generator with OpenAI Structured Outputs integration.

## 🚀 Quick Start

### 1. Set Up Environment

The tests will automatically load environment variables from:
- `DungeonMindServer/.env.development` (preferred for testing)
- `DungeonMindServer/.env.production` (for production validation) 
- `DungeonMindServer/env.development` (legacy fallback)
- `DungeonMindServer/env.production` (legacy fallback)
- `DungeonMindServer/.env` (final fallback)

Make sure your environment file contains:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 2. Install Dependencies

```bash
# Using UV (recommended)
cd DungeonMindServer
uv add pytest pydantic openai python-dotenv pytest-asyncio --group dev

# Or using pip
pip install pytest pydantic openai python-dotenv pytest-asyncio
```

### 3. Run Tests

```bash
# From DungeonMindServer directory:

# Easy way - use the test runner
uv run python tests/statblockgenerator/run_tests.py unit

# Or use pytest directly
uv run python -m pytest tests/statblockgenerator/ -v

# For specific test types
uv run python tests/statblockgenerator/run_tests.py live  # Requires API key
uv run python tests/statblockgenerator/run_tests.py fast # All fast tests
```

## 📋 Test Categories

### Unit Tests (Fast)
- **File**: `test_statblock_structured_outputs.py`
- **Purpose**: Test individual components without API calls
- **Runtime**: < 5 seconds
- **Run**: `python run_tests.py unit`

Tests include:
- Prompt generation and validation
- Pydantic model validation and schema generation
- Basic StatBlock generator functionality (mocked)
- Ability score calculations
- Challenge rating validation

### Performance Tests
- **File**: `test_performance_comparison.py`
- **Purpose**: Compare old vs new approach performance
- **Runtime**: < 10 seconds
- **Run**: `python run_tests.py fast`

Tests include:
- Model creation and validation speed
- JSON schema generation performance
- Memory usage analysis
- Error handling performance
- Reliability improvements verification

### Live API Tests (Slow)
- **File**: `test_live_generation.py`
- **Purpose**: Test with real OpenAI API calls
- **Runtime**: 30-60 seconds
- **Requirements**: Valid `OPENAI_API_KEY`
- **Run**: `python run_tests.py live`

Tests include:
- Simple creature generation
- Spellcaster generation with spells
- Legendary creature generation
- Complex creatures with all features
- Challenge rating accuracy
- Error condition handling

## 🎯 Running Specific Tests

### Run All Fast Tests
```bash
# From DungeonMindServer directory
uv run python tests/statblockgenerator/run_tests.py fast
```

### Run Only Unit Tests
```bash
uv run python tests/statblockgenerator/run_tests.py unit
```

### Run Live API Tests
```bash
uv run python tests/statblockgenerator/run_tests.py live
```

### Run All Tests
```bash
uv run python tests/statblockgenerator/run_tests.py all
```

### Run Specific Test File
```bash
uv run python -m pytest tests/statblockgenerator/test_statblock_structured_outputs.py -v
```

### Run Specific Test Method
```bash
uv run python -m pytest tests/statblockgenerator/test_statblock_structured_outputs.py::TestStatBlockModels::test_ability_scores_modifier_calculation -v
```

## 📊 Test Coverage

### Core Functionality Tested
- ✅ **Prompt Management**: All prompt generation methods
- ✅ **Model Validation**: Complete Pydantic model validation
- ✅ **Schema Generation**: JSON schema for OpenAI Structured Outputs
- ✅ **Generator Logic**: StatBlock generation with mocked API calls
- ✅ **Error Handling**: Various error conditions and edge cases
- ✅ **Performance**: Speed and memory usage comparisons

### OpenAI Integration Tested
- ✅ **Structured Outputs**: Direct Pydantic model generation
- ✅ **Schema Compliance**: Automatic validation by OpenAI
- ✅ **Error Handling**: Refusals and incomplete responses
- ✅ **Model Consistency**: Multiple generations produce valid results

### D&D 5e Compliance Tested
- ✅ **Ability Scores**: Proper ranges and modifier calculations
- ✅ **Challenge Rating**: Validation of CR formats and calculations
- ✅ **Required Fields**: All essential D&D 5e statblock components
- ✅ **Optional Features**: Spellcasting, legendary actions, etc.

## 🔧 Test Configuration

### Environment Variables
```bash
# Required for live tests
OPENAI_API_KEY=sk-...

# Optional - affects test behavior
ENVIRONMENT=development|production
```

### Pytest Markers
- `@pytest.mark.unit` - Unit tests (fast)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Tests that take >5 seconds
- `@pytest.mark.live` - Tests requiring API calls

### Test Fixtures
- `openai_available` - Boolean indicating if API key is available
- `test_environment` - Environment information
- `sample_creature_request` - Basic creature generation request
- `sample_spellcaster_request` - Spellcaster generation request
- `sample_legendary_request` - Legendary creature generation request

## 📈 Performance Benchmarks

### Expected Performance (on typical hardware)
- **Unit Tests**: ~2-5 seconds for full suite
- **Performance Tests**: ~5-10 seconds
- **Live API Tests**: ~30-60 seconds (depends on OpenAI response time)

### Performance Comparisons Tested
- Model creation: 100 StatBlocks in <1 second
- Schema generation: <100ms
- Validation: 100 validations in <1 second
- Memory usage: <10MB for 50 complex statblocks

## 🐛 Debugging Tests

### Run with Verbose Output
```bash
python run_tests.py unit -v
```

### Run with Debug Prints
```bash
pytest test_live_generation.py::test_simple_creature_generation -v -s
```

### Run Single Test with Full Traceback
```bash
pytest test_statblock_structured_outputs.py::TestStatBlockModels::test_statblock_details_valid_creation -v --tb=long
```

## 🏗️ Adding New Tests

### Unit Test Template
```python
class TestNewFeature:
    def setup_method(self):
        self.component = NewComponent()
    
    def test_basic_functionality(self):
        result = self.component.process()
        assert result is not None
```

### Live Test Template
```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_new_live_feature(self):
    generator = StatBlockGenerator()
    assert generator.openai_client is not None
    
    # Your test here
    result = await generator.new_method()
    assert result["success"]
```

## 🚨 Common Issues

### Tests Skipped
- **Cause**: No OpenAI API key found
- **Solution**: Add `OPENAI_API_KEY` to your environment file

### Import Errors
- **Cause**: Missing dependencies
- **Solution**: `pip install pytest pydantic openai python-dotenv`

### Slow Tests Timeout
- **Cause**: OpenAI API response delays
- **Solution**: Check internet connection and API key validity

### Permission Errors
- **Cause**: Test runner script not executable
- **Solution**: `chmod +x run_tests.py`

## 📝 Test Reports

### Generate Coverage Report
```bash
pip install pytest-cov
pytest --cov=statblockgenerator --cov-report=html
```

### Generate Performance Report
```bash
python run_tests.py test_performance_comparison.py -v -s
```

## 🎉 Success Metrics

### Unit Tests Should:
- ✅ All pass in <5 seconds
- ✅ 100% success rate
- ✅ Cover all major components

### Performance Tests Should:
- ✅ Demonstrate significant improvements over old approach
- ✅ Show reasonable memory usage
- ✅ Complete in <10 seconds

### Live Tests Should:
- ✅ Generate valid D&D 5e statblocks
- ✅ Handle all requested features (spells, legendary actions)
- ✅ Produce different results for different inputs
- ✅ Pass validation checks

This test suite ensures the StatBlock Generator with OpenAI Structured Outputs is working correctly, efficiently, and reliably! 🎲✨

