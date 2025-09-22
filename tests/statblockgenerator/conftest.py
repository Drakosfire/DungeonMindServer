"""
Pytest configuration for StatBlock Generator tests
Handles environment loading and test fixtures
"""

import pytest
import os
from pathlib import Path
from dotenv import load_dotenv


def pytest_configure(config):
    """Configure pytest for StatBlock Generator tests"""
    
    # Get the DungeonMindServer root directory
    server_root = Path(__file__).parent.parent.parent
    
    # Try to load environment variables
    env_loaded = False
    
    # Try to load environment variables in order of preference
    env_files_to_try = [
        server_root / ".env.development",
        server_root / ".env.production", 
        server_root / "env.development",
        server_root / "env.production",
        server_root / ".env"
    ]
    
    for env_path in env_files_to_try:
        if env_path.exists():
            load_dotenv(env_path)
            env_loaded = True
            print(f"Loaded environment from {env_path}")
            break
    
    if not env_loaded:
        print("No environment file found - some tests may be skipped")
    
    # Print environment status for debugging
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print(f"OpenAI API key loaded: {openai_key[:8]}...")
    else:
        print("No OpenAI API key found - live tests will be skipped")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle slow tests"""
    
    # Add slow marker to items that don't have it but should
    for item in items:
        # Mark live generation tests as slow
        if "test_live_generation" in str(item.fspath):
            item.add_marker(pytest.mark.slow)
        
        # Mark integration tests as slow
        if "integration" in item.name.lower():
            item.add_marker(pytest.mark.slow)


@pytest.fixture(scope="session")
def openai_available():
    """Fixture to check if OpenAI API is available"""
    return bool(os.getenv("OPENAI_API_KEY"))


@pytest.fixture(scope="session")
def test_environment():
    """Fixture providing test environment information"""
    return {
        "openai_available": bool(os.getenv("OPENAI_API_KEY")),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "server_root": Path(__file__).parent.parent.parent
    }


@pytest.fixture
def sample_creature_request():
    """Fixture providing a sample creature generation request"""
    from statblockgenerator.models.statblock_models import CreatureGenerationRequest
    
    return CreatureGenerationRequest(
        description="A brave knight wielding a magical sword",
        challenge_rating_target="2",
        include_spells=False,
        include_legendary=False
    )


@pytest.fixture
def sample_spellcaster_request():
    """Fixture providing a sample spellcaster generation request"""
    from statblockgenerator.models.statblock_models import CreatureGenerationRequest
    
    return CreatureGenerationRequest(
        description="A wise wizard who studies ancient arcane secrets",
        challenge_rating_target="5",
        include_spells=True,
        include_legendary=False
    )


@pytest.fixture
def sample_legendary_request():
    """Fixture providing a sample legendary creature generation request"""
    from statblockgenerator.models.statblock_models import CreatureGenerationRequest
    
    return CreatureGenerationRequest(
        description="An ancient dragon that hoards magical artifacts",
        challenge_rating_target="12",
        include_spells=False,
        include_legendary=True
    )


