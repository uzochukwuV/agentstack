import pytest
from unittest.mock import MagicMock
from skills.base import BaseSkill
from skills.aave import AaveV4Skill
from skills.registry import load_skills_for_user, get_tools_for_user
from langchain_core.tools import BaseTool

def test_1_base_skill_is_abstract():
    with pytest.raises(TypeError):
        BaseSkill()

def test_2_aave_implements_methods():
    skill = AaveV4Skill()
    tools = skill.get_tools()
    assert len(tools) > 0

def test_3_tools_have_name_and_description():
    skill = AaveV4Skill()
    tools = skill.get_tools()
    for t in tools:
        assert hasattr(t, "name")
        assert hasattr(t, "description")
        # In langchain_core >= 0.2.x, tools are callable or invokeable.
        # But we just need to know it's a valid LangGraph tool (inherits from BaseTool or has invoke).
        assert isinstance(t, BaseTool) or callable(t) or hasattr(t, "invoke")

def test_4_load_skills_correct():
    mock_w3 = MagicMock()
    skills = load_skills_for_user("0x123", [1, 3], mock_w3)
    assert len(skills) == 2
    types = [type(s).__name__ for s in skills]
    assert "AaveV4Skill" in types
    assert "GMXV2Skill" in types

def test_5_unknown_id_handled_gracefully():
    skills = load_skills_for_user("0x123", [99])
    assert len(skills) == 0

def test_6_get_tools_flattens_and_dedupes():
    from skills.gmx import GMXV2Skill
    skill1 = AaveV4Skill()
    skill2 = GMXV2Skill()
    tools = get_tools_for_user([skill1, skill1, skill2])
    names = [t.name for t in tools]
    assert len(names) == len(set(names))
    assert len(tools) == 3

def test_7_health_check_resilient():
    mock_w3 = MagicMock()
    mock_w3.is_connected.side_effect = Exception("Connection error")
    skill = AaveV4Skill(mock_w3)
    assert skill.health_check() is False

def test_8_position_summary_schema():
    skill = AaveV4Skill()
    summary = skill.get_position_summary("0x123")
    assert "protocol" in summary
    assert "supplied" in summary
    assert "borrowed" in summary
