"""
Prompt management system for versioned AI prompts
"""
import logging
import json
import yaml
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class PromptTemplate:
    """Represents a versioned prompt template"""
    
    def __init__(self, template_data: Dict[str, Any]):
        self.version = template_data.get('version', '1.0.0')
        self.name = template_data.get('name', 'unnamed')
        self.description = template_data.get('description', '')
        self.template = template_data.get('template', '')
        self.max_tokens = template_data.get('max_tokens', 4000)
        self.validation = template_data.get('validation', {})
        self.model_compatibility = template_data.get('model_compatibility', ['gpt-4o'])
        
        logger.info(f"Loaded prompt template '{self.name}' v{self.version}")
    
    def render(self, context: Dict[str, Any]) -> str:
        """
        Render the prompt template with given context
        
        Args:
            context: Variables to substitute in the template
            
        Returns:
            Rendered prompt string
        """
        try:
            # Simple string formatting for now
            rendered = self.template.format(**context)
            logger.debug(f"Rendered prompt for context keys: {list(context.keys())}")
            return rendered
        except KeyError as e:
            raise ValueError(f"Missing required context variable: {e}")
        except Exception as e:
            raise ValueError(f"Error rendering prompt template: {e}")
    
    def validate_response(self, response: str) -> Dict[str, Any]:
        """
        Validate AI response against template schema
        
        Args:
            response: Raw AI response string
            
        Returns:
            Validated and parsed response data
        """
        try:
            # Extract JSON from response
            parsed_data = self._extract_json_from_response(response)
            
            # Validate required fields
            required_fields = self.validation.get('required_fields', [])
            for field in required_fields:
                if field not in parsed_data:
                    raise ValueError(f"Missing required field: {field}")
                if not parsed_data[field]:
                    raise ValueError(f"Empty required field: {field}")
            
            # Validate specific field types and constraints
            self._validate_field_constraints(parsed_data)
            
            logger.info("Response validation passed")
            return parsed_data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}")
        except Exception as e:
            raise ValueError(f"Response validation failed: {e}")
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON object from AI response text"""
        # Try to parse the entire response as JSON first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass
        
        # Look for JSON blocks in markdown format
        json_pattern = r'```json\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, response, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Look for any JSON-like object in the response
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, response, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        raise json.JSONDecodeError("No valid JSON found in response", response, 0)
    
    def _validate_field_constraints(self, data: Dict[str, Any]) -> None:
        """Validate field-specific constraints"""
        validation = self.validation
        
        # Validate rarity values
        if 'rarity_values' in validation and 'Rarity' in data:
            valid_rarities = validation['rarity_values']
            if data['Rarity'] not in valid_rarities:
                raise ValueError(f"Invalid rarity '{data['Rarity']}'. Must be one of: {valid_rarities}")
        
        # Validate value patterns
        if 'value_patterns' in validation and 'Value' in data:
            value = data['Value']
            patterns = validation['value_patterns']
            if not any(re.search(pattern, value) for pattern in patterns):
                logger.warning(f"Value '{value}' may not match expected patterns: {patterns}")
        
        # Validate properties type
        if 'properties_type' in validation and 'Properties' in data:
            if validation['properties_type'] == 'array':
                if not isinstance(data['Properties'], list):
                    raise ValueError("Properties must be an array/list")
        
        # Validate length constraints
        if 'max_description_length' in validation and 'Description' in data:
            max_len = validation['max_description_length']
            if len(data['Description']) > max_len:
                logger.warning(f"Description length ({len(data['Description'])}) exceeds recommended maximum ({max_len})")
        
        if 'min_sd_prompt_length' in validation and 'SD Prompt' in data:
            min_len = validation['min_sd_prompt_length']
            if len(data['SD Prompt']) < min_len:
                logger.warning(f"SD Prompt length ({len(data['SD Prompt'])}) below recommended minimum ({min_len})")

class PromptManager:
    """Manages versioned prompt templates"""
    
    def __init__(self):
        self.templates: Dict[str, Dict[str, PromptTemplate]] = {}
        self._load_builtin_templates()
        logger.info("PromptManager initialized")
    
    def _load_builtin_templates(self):
        """Load built-in prompt templates"""
        # For now, create the item generation template directly
        item_generation_template = {
            "version": "2.0.0",
            "name": "item_generation",
            "description": "Generate D&D item descriptions with consistent formatting",
            "max_tokens": 4000,
            "model_compatibility": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
            "template": """**Purpose**: Generate a structured inventory entry for a D&D item as a JSON object.

**Item to Generate**: {item_name}

**Requirements**:
1. Name: Use the exact item name provided: '{item_name}'
2. Type: Appropriate D&D item category (Weapon, Armor, Consumable, Wondrous Item, etc.)
3. Rarity: One of: Common, Uncommon, Rare, Very Rare, Legendary
4. Value: Appropriate monetary value with currency (cp, sp, ep, gp, pp)
5. Properties: List of mechanical effects and abilities
6. Weight: Realistic weight for the item
7. Description: Brief, punchy description (2-3 sentences)
8. Quote: Rich, atmospheric quote from someone who has used/encountered the item
9. SD Prompt: Detailed image generation prompt for creating artwork

**Value Guidelines**:
- Common items: 1-100 gp
- Uncommon items: 101-500 gp  
- Rare items: 501-5000 gp
- Very Rare items: 5001-50000 gp
- Legendary items: 50001+ gp

**SD Prompt Requirements**:
Create detailed, comprehensive image prompts that include:
- Subject: Detailed description of the item's appearance, materials, and unique features
- Art Style: Specify artistic approach (fantasy concept art, photorealistic, etc.)
- Composition: Camera angle, framing, perspective
- Lighting: Detailed lighting setup (dramatic rim lighting, soft ethereal glow, etc.)
- Atmosphere: Mood and environmental elements
- Colors: Specific color palette and materials
- Quality Tags: Include "masterpiece", "highly detailed", "8k resolution"

**Output Format**:
Return ONLY a valid JSON object with these exact keys:
```json
{{
  "Name": "string",
  "Type": "string",
  "Rarity": "string", 
  "Value": "string",
  "Properties": ["string"],
  "Weight": "string",
  "Description": "string",
  "Quote": "string",
  "SD Prompt": "string"
}}
```""",
            "validation": {
                "required_fields": ["Name", "Type", "Rarity", "Value", "Properties", "Weight", "Description", "Quote", "SD Prompt"],
                "rarity_values": ["Common", "Uncommon", "Rare", "Very Rare", "Legendary"],
                "value_patterns": [r"\d+\s*(cp|sp|ep|gp|pp)"],
                "properties_type": "array",
                "max_description_length": 500,
                "max_quote_length": 200,
                "min_sd_prompt_length": 100
            }
        }
        
        # Store the template
        template = PromptTemplate(item_generation_template)
        if "item_generation" not in self.templates:
            self.templates["item_generation"] = {}
        self.templates["item_generation"]["2.0.0"] = template
        self.templates["item_generation"]["latest"] = template
        
        logger.info("Built-in templates loaded successfully")
    
    def get_prompt(self, template_name: str, version: str = "latest") -> PromptTemplate:
        """
        Get a specific prompt template by name and version
        
        Args:
            template_name: Name of the template
            version: Version of the template
            
        Returns:
            PromptTemplate instance
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
        
        if version not in self.templates[template_name]:
            available_versions = list(self.templates[template_name].keys())
            raise ValueError(f"Version '{version}' not found for template '{template_name}'. Available: {available_versions}")
        
        return self.templates[template_name][version]
    
    def render_prompt(self, template_name: str, context: Dict[str, Any], version: str = "latest") -> str:
        """
        Render a prompt template with given context
        
        Args:
            template_name: Name of the template
            context: Variables to substitute
            version: Template version
            
        Returns:
            Rendered prompt string
        """
        template = self.get_prompt(template_name, version)
        return template.render(context)
    
    def validate_response(self, template_name: str, response: str, version: str = "latest") -> Dict[str, Any]:
        """
        Validate AI response against template schema
        
        Args:
            template_name: Name of the template used
            response: Raw AI response
            version: Template version used
            
        Returns:
            Validated response data
        """
        template = self.get_prompt(template_name, version)
        return template.validate_response(response)
    
    def list_templates(self) -> Dict[str, List[str]]:
        """
        List all available templates and their versions
        
        Returns:
            Dictionary mapping template names to version lists
        """
        return {
            name: list(versions.keys()) 
            for name, versions in self.templates.items()
        }

# Global prompt manager instance
prompt_manager = PromptManager()