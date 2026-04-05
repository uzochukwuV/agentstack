from typing import List, Any
from .base import BaseSkill
from .aave import AaveV4Skill
from .gmx import GMXV2Skill

SKILL_MAP = {
    AaveV4Skill.SKILL_ID: AaveV4Skill,
    GMXV2Skill.SKILL_ID: GMXV2Skill
}

def load_skills_for_user(user_address: str, skill_ids: List[int], web3_provider=None) -> List[BaseSkill]:
    skills = []
    for sid in skill_ids:
        skill_class = SKILL_MAP.get(sid)
        if skill_class:
            skills.append(skill_class(web3_provider))
    return skills

def get_tools_for_user(skills: List[BaseSkill]) -> List[Any]:
    tools = []
    seen = set()
    for skill in skills:
        for t in skill.get_tools():
            if t.name not in seen:
                tools.append(t)
                seen.add(t.name)
    return tools
