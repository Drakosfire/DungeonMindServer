"""
Prompt management for StatBlock Generator
"""

from .statblock_prompts import StatBlockPromptManager

# Global prompt manager instance
statblock_prompt_manager = StatBlockPromptManager()

__all__ = ["statblock_prompt_manager"]
