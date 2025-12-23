"""
Core Player Character Generator logic using GenerationEngine

Generates AI preferences for D&D 5e character creation.
"""

import logging
import json
import os
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from generationengine.services.text_service import TextGenerationService
from generationengine.models.requests import TextGenerationRequest, TextModel

from .models.pcg_models import (
    GenerationInput,
    GenerationConstraints,
    AiPreferences,
    PreferenceGenerationRequest,
)
from .prompts.pcg_prompts import (
    PCGPromptManager,
    create_mock_fighter_constraints,
    create_mock_wizard_constraints,
)
from .rule_engine import PCGRuleEngine

logger = logging.getLogger(__name__)


class PlayerCharacterGenerator:
    """
    Main Player Character generation engine
    
    Generates AI preferences based on user-provided character concept
    and rule-engine constraints.
    """

    def __init__(self):
        self.prompt_manager = PCGPromptManager()
        self.rule_engine = PCGRuleEngine()
        self.text_service = None
        # Use GPT_5_1 for now (GPT-5.2 not yet in TextModel enum)
        # TODO: Add GPT_5_2 to TextModel enum if available in Responses API
        self.model = TextModel.GPT_5_1
        self.model_name = "gpt-5.1"  # For logging/health check

        # Initialize TextGenerationService if API key is available
        try:
            self.text_service = TextGenerationService()
            logger.info(
                "PlayerCharacterGenerator initialized | model=%s | module_path=%s",
                self.model_name,
                __file__,
            )
        except ValueError as e:
            logger.warning(f"TextGenerationService initialization failed: {str(e)}")
            self.text_service = None

    async def generate_preferences(
        self,
        request: PreferenceGenerationRequest
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Generate AI preferences for character creation

        Args:
            request: Generation request with input and optional constraints

        Returns:
            Tuple of (success, result_data)
        """
        try:
            concept = request.input.concept
            logger.info(f"Generating preferences for: {concept[:50]}...")

            if not self.text_service:
                return False, {"error": "TextGenerationService not initialized"}

            # Get or create constraints
            if request.constraints:
                constraints = request.constraints
            else:
                try:
                    constraints = self.rule_engine.get_constraints(request.input)
                except Exception as e:
                    # Fallback to mock constraints to keep the endpoint usable while we expand catalogs.
                    logger.warning("PCG rule engine failed; falling back to mock constraints | error=%s", str(e))
                    constraints = self._get_mock_constraints(request.input.class_id)
                    if not constraints:
                        return False, {"error": f"No constraints available for class: {request.input.class_id}"}

            # Build prompts
            system_prompt = self.prompt_manager.get_system_prompt()
            user_prompt = self.prompt_manager.build_preference_prompt(
                request.input,
                constraints
            )

            # Call GenerationEngine
            response = await self._call_openai(system_prompt, user_prompt)

            if not response["success"]:
                return False, response

            raw_response = response["content"]

            # Parse JSON from response
            preferences = self._parse_preferences(raw_response)
            if not preferences:
                return False, {
                    "error": "Failed to parse preferences from AI response",
                    "rawResponse": raw_response
                }

            logger.info(f"Successfully generated preferences for: {preferences.character.name}")

            return True, {
                "preferences": preferences.model_dump(by_alias=True),
                "rawResponse": raw_response,
                "generationInfo": {
                    "promptVersion": self.prompt_manager.version,
                    "model": self.model_name,
                    "timestamp": datetime.now().isoformat(),
                    "promptTokens": response.get("promptTokens", 0),
                    "completionTokens": response.get("completionTokens", 0),
                    "totalTokens": response.get("totalTokens", 0),
                }
            }

        except Exception as e:
            logger.error(f"Error generating preferences: {str(e)}")
            return False, {"error": "Generation failed", "details": str(e)}

    async def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> Dict[str, Any]:
        """
        Call GenerationEngine TextGenerationService for preference generation

        Args:
            system_prompt: System message
            user_prompt: User message with constraints and concept

        Returns:
            Dict with success, content, and token counts
        """
        try:
            logger.debug(f"Calling GenerationEngine with prompt length: {len(user_prompt)} chars")

            # Build TextGenerationRequest
            # Note: max_tokens not supported in Responses API - removed
            ge_request = TextGenerationRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=self.model,
                temperature=0.7,
            )

            logger.info(
                "Calling GenerationEngine TextGenerationService | model=%s",
                self.model_name,
            )

            # Call GenerationEngine
            response = await self.text_service.generate(
                ge_request,
                service_name="playercharactergenerator"
            )

            if not response.success:
                error_msg = response.error.message if response.error else "Unknown error"
                logger.error(f"GenerationEngine error: {error_msg}")
                return {"success": False, "error": error_msg}

            # Extract content and metrics
            content = response.content
            metrics = response.metrics

            # Note: Responses API may not provide prompt/completion breakdown
            # Use total tokens for all counts (approximation)
            total_tokens = metrics.tokens_used if metrics else 0
            logger.info(f"GenerationEngine response received: {total_tokens} tokens")

            return {
                "success": True,
                "content": content,
                # Responses API doesn't provide prompt/completion breakdown
                # Use total tokens as approximation (may need adjustment)
                "promptTokens": total_tokens,  # Approximation
                "completionTokens": total_tokens,  # Approximation
                "totalTokens": total_tokens,
            }

        except Exception as e:
            logger.error(f"GenerationEngine API error: {str(e)}")
            return {"success": False, "error": str(e)}

    def _parse_preferences(self, raw_response: str) -> Optional[AiPreferences]:
        """
        Parse AI response into AiPreferences model

        Args:
            raw_response: Raw text from OpenAI

        Returns:
            AiPreferences or None if parsing fails
        """
        try:
            # Extract JSON from markdown code block if present
            json_str = raw_response
            if "```json" in raw_response:
                start = raw_response.find("```json") + 7
                end = raw_response.find("```", start)
                json_str = raw_response[start:end].strip()
            elif "```" in raw_response:
                start = raw_response.find("```") + 3
                end = raw_response.find("```", start)
                json_str = raw_response[start:end].strip()

            # Parse JSON
            data = json.loads(json_str)

            # Create Pydantic model
            preferences = AiPreferences(**data)
            return preferences

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Raw response: {raw_response[:500]}")
            return None
        except Exception as e:
            logger.error(f"Preference parse error: {e}")
            return None

    def _get_mock_constraints(self, class_id: str) -> Optional[GenerationConstraints]:
        """
        Get mock constraints for testing

        TODO: Replace with actual Rule Engine integration
        """
        mock_map = {
            "fighter": create_mock_fighter_constraints,
            "wizard": create_mock_wizard_constraints,
        }

        if class_id not in mock_map:
            # Return fighter constraints as fallback
            logger.warning(f"No mock constraints for {class_id}, using fighter")
            constraints_dict = create_mock_fighter_constraints()
        else:
            constraints_dict = mock_map[class_id]()

        try:
            return GenerationConstraints(**constraints_dict)
        except Exception as e:
            logger.error(f"Failed to create constraints: {e}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the generator is healthy

        Returns:
            Health status dict
        """
        return {
            "status": "healthy" if self.text_service else "degraded",
            "text_service_configured": self.text_service is not None,
            "prompt_version": self.prompt_manager.version,
            "model": self.model_name,
            "module_path": __file__,
        }

