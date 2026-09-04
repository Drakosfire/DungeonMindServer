"""
Core Player Character Generator logic using GenerationEngine

Generates AI preferences for D&D 5e character creation.
"""

import logging
import json
import os
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from generationengine import GenerationEngineError, TextRequest
from shared.generation import get_generation_client
from shared.inference_policy import inference_for

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
        self.model_name = "gpt-5.1"
        self.client = get_generation_client()
        logger.info(
            "PlayerCharacterGenerator initialized | model=%s | module_path=%s",
            self.model_name,
            __file__,
        )

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
            response = await self._generate_preferences_text(system_prompt, user_prompt)

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

    async def _generate_preferences_text(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> Dict[str, Any]:
        """Call GenerationEngine for preference generation and return product-shaped tokens."""
        try:
            action = inference_for("pcg_preference_generation")
            logger.info(
                "Calling GenerationEngine | profile=%s model=%s",
                action.profile.value,
                self.model_name,
            )
            result = await self.client.generate_text(
                TextRequest(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=action.profile,
                    model=action.model,
                    temperature=0.7,
                )
            )
            obs = result.observation
            input_tokens = obs.input_tokens or 0
            output_tokens = obs.output_tokens or 0
            total_tokens = input_tokens + output_tokens
            logger.info(
                "GenerationEngine response received: input=%s output=%s",
                input_tokens,
                output_tokens,
            )
            return {
                "success": True,
                "content": result.text or "",
                "promptTokens": input_tokens,
                "completionTokens": output_tokens,
                "totalTokens": total_tokens,
            }
        except GenerationEngineError as error:
            logger.error("GenerationEngine error: %s", error.failure.message)
            return {"success": False, "error": error.failure.message}
        except Exception as e:
            logger.error("GenerationEngine API error: %s", str(e))
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
            "status": "healthy" if os.getenv("OPENAI_API_KEY") else "degraded",
            "text_service_configured": bool(os.getenv("OPENAI_API_KEY")),
            "prompt_version": self.prompt_manager.version,
            "model": self.model_name,
            "module_path": __file__,
        }

