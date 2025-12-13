"""
Core Player Character Generator logic using OpenAI

Generates AI preferences for D&D 5e character creation.
"""

import logging
import json
import os
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from openai import OpenAI

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

logger = logging.getLogger(__name__)


class PlayerCharacterGenerator:
    """
    Main Player Character generation engine
    
    Generates AI preferences based on user-provided character concept
    and rule-engine constraints.
    """

    def __init__(self):
        self.prompt_manager = PCGPromptManager()
        self.openai_client = None
        self.model = "gpt-5.2"
        # Some newer OpenAI models reject `max_tokens` and require `max_completion_tokens`.
        # Keep the param name explicit so logs/health can prove what the running server uses.
        self.token_limit_param_name = "max_completion_tokens"

        # Initialize OpenAI client if API key is available
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
            logger.info(
                "PlayerCharacterGenerator initialized | model=%s | token_limit_param=%s | module_path=%s",
                self.model,
                self.token_limit_param_name,
                __file__,
            )
        else:
            logger.warning("No OpenAI API key found - AI generation will not work")

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

            if not self.openai_client:
                return False, {"error": "OpenAI client not initialized"}

            # Get or create constraints
            if request.constraints:
                constraints = request.constraints
            else:
                # Use mock constraints based on class for now
                # TODO: Integrate with actual Rule Engine
                constraints = self._get_mock_constraints(request.input.class_id)
                if not constraints:
                    return False, {"error": f"No constraints available for class: {request.input.class_id}"}

            # Build prompts
            system_prompt = self.prompt_manager.get_system_prompt()
            user_prompt = self.prompt_manager.build_preference_prompt(
                request.input,
                constraints
            )

            # Call OpenAI
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
                    "model": self.model,
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
        Call OpenAI API for preference generation

        Args:
            system_prompt: System message
            user_prompt: User message with constraints and concept

        Returns:
            Dict with success, content, and token counts
        """
        try:
            logger.debug(f"Calling OpenAI with prompt length: {len(user_prompt)} chars")

            request_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                self.token_limit_param_name: 2000,
            }

            # Explicit breadcrumb for debugging OpenAI 400s about token parameter naming.
            logger.info(
                "Calling OpenAI chat.completions | model=%s | token_limit_param=%s",
                self.model,
                self.token_limit_param_name,
            )

            response = self.openai_client.chat.completions.create(**request_kwargs)

            content = response.choices[0].message.content
            usage = response.usage

            logger.info(f"OpenAI response received: {usage.total_tokens} tokens")

            return {
                "success": True,
                "content": content,
                "promptTokens": usage.prompt_tokens,
                "completionTokens": usage.completion_tokens,
                "totalTokens": usage.total_tokens,
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
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
            "status": "healthy" if self.openai_client else "degraded",
            "openai_configured": self.openai_client is not None,
            "prompt_version": self.prompt_manager.version,
            "model": self.model,
            "token_limit_param": self.token_limit_param_name,
            "module_path": __file__,
        }

