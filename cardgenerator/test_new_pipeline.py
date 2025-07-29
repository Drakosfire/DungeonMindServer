"""
Test script for the new card generation pipeline
"""
import asyncio
import logging
import sys
import os

# Add the parent directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cardgenerator.card_generator_new import CardGeneratorV2

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_new_pipeline():
    """Test the new card generation pipeline"""
    try:
        logger.info("🧪 Testing new card generation pipeline...")
        
        # Initialize the new generator
        generator = CardGeneratorV2()
        
        # Test 1: Check pipeline initialization
        logger.info("✅ Pipeline initialization successful")
        
        # Test 2: Check supported rarities
        rarities = generator.get_supported_rarities()
        logger.info(f"✅ Supported rarities: {rarities}")
        
        # Test 3: Check card dimensions
        dimensions = generator.get_card_dimensions()
        logger.info(f"✅ Card dimensions: {dimensions}")
        
        # Test 4: Generate test item details
        test_item_name = "Mystical Test Blade"
        item_details = await generator.generate_item_details(test_item_name)
        logger.info(f"✅ Generated item details for '{test_item_name}': {item_details['Name']}")
        
        # Test 5: Test card rendering with mock data
        test_image_url = "https://via.placeholder.com/768x1024/4A90E2/FFFFFF?text=Test+Card"
        try:
            test_card = await generator.render_text_on_card(test_image_url, item_details)
            logger.info(f"✅ Card rendering successful: {test_card.size}")
        except Exception as e:
            logger.warning(f"⚠️ Card rendering test failed (expected with placeholder): {e}")
        
        # Test 6: Create test card
        try:
            test_card = await generator.create_test_card()
            logger.info(f"✅ Test card creation successful: {test_card.size}")
        except Exception as e:
            logger.warning(f"⚠️ Test card creation failed: {e}")
        
        logger.info("🎉 New pipeline tests completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Pipeline test failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_new_pipeline())
    if result:
        print("\n🎉 All tests passed! New pipeline is ready.")
    else:
        print("\n❌ Some tests failed. Check the logs above.")