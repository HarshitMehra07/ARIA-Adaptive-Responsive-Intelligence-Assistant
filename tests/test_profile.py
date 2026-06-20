# tests/test_profile.py

from core.aria_core import ARIACore

from memory.profile_manager import ProfileManager

ARIACore.process(
    "My goal is to become an AI Engineer"
)

ARIACore.process(
    "ARIA is my personal assistant project"
)

ARIACore.process(
    "I go to gym everyday"
)

ProfileManager.show_profile()