"""
Asset Service

Handles static asset management including:
- Example images for Step 2 inspiration
- Border options for Step 3 card frames
- Asset metadata and categorization
- Configuration-driven asset management

This service extracts hardcoded asset data from the monolithic router.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ExampleImage:
    """Example image with metadata"""
    url: str
    name: str
    category: str
    description: str
    id: Optional[str] = None

@dataclass
class BorderOption:
    """Border option with styling information"""
    id: str
    url: str
    name: str
    style: str
    description: str

class AssetService:
    """
    Service for managing card generation assets
    
    Provides:
    - Curated example images for inspiration
    - Border options for card frames
    - Asset categorization and metadata
    """
    
    def __init__(self):
        self._example_images = None
        self._border_options = None
        logger.info("AssetService initialized")
    
    def get_example_images(self) -> List[ExampleImage]:
        """
        Get curated list of example images for Step 2
        
        Returns:
            List of ExampleImage objects with metadata
        """
        if self._example_images is None:
            self._load_example_images()
        
        logger.info(f"Returning {len(self._example_images)} example images")
        return self._example_images
    
    def get_border_options(self) -> List[BorderOption]:
        """
        Get available border options for Step 3
        
        Returns:
            List of BorderOption objects with styling info
        """
        if self._border_options is None:
            self._load_border_options()
        
        logger.info(f"Returning {len(self._border_options)} border options")
        return self._border_options
    
    def get_example_by_category(self, category: str) -> List[ExampleImage]:
        """
        Filter example images by category
        
        Args:
            category: Category to filter by (e.g., "Weapon", "Potion")
            
        Returns:
            List of matching ExampleImage objects
        """
        examples = self.get_example_images()
        filtered = [img for img in examples if img.category.lower() == category.lower()]
        
        logger.info(f"Found {len(filtered)} examples in category '{category}'")
        return filtered
    
    def get_border_by_style(self, style: str) -> List[BorderOption]:
        """
        Filter borders by style
        
        Args:
            style: Style to filter by (e.g., "Dark", "Fire")
            
        Returns:
            List of matching BorderOption objects
        """
        borders = self.get_border_options()
        filtered = [border for border in borders if border.style.lower() == style.lower()]
        
        logger.info(f"Found {len(filtered)} borders in style '{style}'")
        return filtered
    
    def _load_example_images(self):
        """Load example images from configuration"""
        
        # Example image URLs from Cloudflare
        example_urls = [
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/a2f5fcea-1b16-4dc7-1874-3688bf66f900/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/6f37d2ce-74aa-4d4f-c8fd-d2145f6bc700/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8829b2aa-834b-48c2-c4bb-7f4907ced200/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/f10cbb4f-a00b-480f-38ca-1e3d816c5700/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/29dfd4d3-176e-41d4-d69d-36f3d98e6600/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/d8bf9bf2-6a6a-4451-5ff6-01bd7e36e200/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/ae6cb0e0-d91f-428c-7632-c3f1dea26b00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/aeb68105-04fe-42ec-df9d-e232b29d0400/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/3df60f6d-9bc9-40de-a028-169d64319400/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/47f79b37-f43a-419f-99d6-5f8f60ba4100/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/6184f9fd-2374-48ec-0bc8-3da2559d8300/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/567b2937-956f-4d74-7321-55f7640b3e00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/a6d03d18-4202-4e69-4a2d-7c948caa9000/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/7b479f54-94e3-40b5-c214-5de7d56f4a00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/56ce102c-6186-46ad-594a-5861d69e6500/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/907fde65-9de0-4f77-e370-f80b37818800/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/211b4598-e29a-4947-0b30-6355ca45ea00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/271b4e40-1a5f-49fc-eeb3-bfe26be80700/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/1d0d09c9-56ae-4323-b8b7-57e60b697d00/public"
        ]
        
        # Example metadata
        example_items = [
            {"name": "Mystical Sword", "category": "Weapon", "description": "An enchanted blade radiating magical energy"},
            {"name": "Crystal Orb", "category": "Mystical", "description": "A glowing sphere of arcane power"},
            {"name": "Ancient Tome", "category": "Scroll", "description": "A weathered spellbook filled with secrets"},
            {"name": "Healing Elixir", "category": "Potion", "description": "A shimmering red potion of restoration"},
            {"name": "Dragon Scale", "category": "Material", "description": "A protective scale from an ancient wyrm"},
            {"name": "Runic Dagger", "category": "Weapon", "description": "A ceremonial blade inscribed with runes"},
            {"name": "Magic Amulet", "category": "Accessory", "description": "A pendant crackling with magical energy"},
            {"name": "Wizard Staff", "category": "Weapon", "description": "An ornate staff topped with a crystal"},
            {"name": "Golden Chalice", "category": "Treasure", "description": "An ornate cup of immense value"},
            {"name": "Fire Gem", "category": "Material", "description": "A gem containing elemental fire"},
            {"name": "Battle Axe", "category": "Weapon", "description": "A mighty weapon forged for combat"},
            {"name": "Spell Scroll", "category": "Scroll", "description": "Ancient parchment containing powerful magic"},
            {"name": "Shield of Valor", "category": "Armor", "description": "A protective barrier imbued with courage"},
            {"name": "Mystic Ring", "category": "Accessory", "description": "A band of power worn by ancient mages"},
            {"name": "Enchanted Bow", "category": "Weapon", "description": "A ranged weapon blessed by the forest"},
            {"name": "Crown of Kings", "category": "Treasure", "description": "Royal headwear of legendary rulers"},
            {"name": "Void Crystal", "category": "Material", "description": "A dark gem from beyond the veil"},
            {"name": "War Hammer", "category": "Weapon", "description": "A crushing weapon of divine might"},
            {"name": "Cloak of Shadows", "category": "Armor", "description": "Fabric that bends light and shadow"}
        ]
        
        # Combine URLs with metadata
        self._example_images = []
        for i, url in enumerate(example_urls[:len(example_items)]):
            if i < len(example_items):
                self._example_images.append(ExampleImage(
                    url=url,
                    name=example_items[i]["name"],
                    category=example_items[i]["category"],
                    description=example_items[i]["description"],
                    id=f"example_{i+1}"
                ))
        
        logger.info(f"Loaded {len(self._example_images)} example images")
    
    def _load_border_options(self):
        """Load border options from configuration"""
        
        # Border URLs from Cloudflare
        border_urls = [
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/90293844-4eec-438f-2ea1-c89d9cb84700/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/54d94248-e737-452c-bffd-2d425f803000/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/d0872a5e-91a0-41f8-f819-3d1a0931c900/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/8c113608-2389-4588-2090-d0192c539b00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/e6253513-b33d-4d9c-1631-38cc46199d00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/879e240e-4491-42de-8729-5f8899841e00/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/56e91eca-d530-483f-4b62-277486097200/public",
            "https://imagedelivery.net/SahcvrNe_-ej4lTB6vsAZA/5fdfd8cd-51c3-4dde-2d3f-f1b463f05200/public"
        ]
        
        # Border style metadata
        border_styles = [
            {"name": "Onyx Shadow", "style": "Dark", "description": "Deep black borders with shadowed edges"},
            {"name": "Flaming Copper", "style": "Fire", "description": "Warm copper tones with flame motifs"},
            {"name": "Sandstone Classic", "style": "Earth", "description": "Natural stone texture with carved details"},
            {"name": "Emerald Intricate", "style": "Nature", "description": "Green borders with leaf and vine patterns"},
            {"name": "Sapphire Ink", "style": "Water", "description": "Blue borders with flowing water designs"},
            {"name": "Crystal Teal", "style": "Ice", "description": "Cool crystalline patterns in teal"},
            {"name": "Royal Gold", "style": "Luxury", "description": "Ornate golden borders fit for royalty"},
            {"name": "Mystic Silver", "style": "Arcane", "description": "Silver borders with magical rune accents"}
        ]
        
        # Combine URLs with metadata
        self._border_options = []
        for i, url in enumerate(border_urls[:len(border_styles)]):
            if i < len(border_styles):
                self._border_options.append(BorderOption(
                    id=f"border_{i+1}",
                    url=url,
                    name=border_styles[i]["name"],
                    style=border_styles[i]["style"],
                    description=border_styles[i]["description"]
                ))
        
        logger.info(f"Loaded {len(self._border_options)} border options")
    
    def get_asset_categories(self) -> List[str]:
        """Get list of available asset categories"""
        examples = self.get_example_images()
        categories = list(set(img.category for img in examples))
        return sorted(categories)
    
    def get_border_styles(self) -> List[str]:
        """Get list of available border styles"""
        borders = self.get_border_options()
        styles = list(set(border.style for border in borders))
        return sorted(styles)

# Export the service instance
asset_service = AssetService()