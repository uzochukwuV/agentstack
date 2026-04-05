import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from agent.state import AgentState
from agent.graph import create_agent_graph

@pytest.fixture
def mock_get_positions():
    def _mock(address):
        return {
            "Aave": {"supplied": 1000},
            "_health_factor": 2.0,
            "_utilisation_rate": 40.0
        }
    return _mock

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.return_value = AIMessage(content="MOCK_ACTION")
    return llm

def test_1_graph_compiles_with_memory_saver(mock_llm, mock_get_positions):
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    assert app is not None

def test_2_fetch_positions_updates_state(mock_llm, mock_get_positions):
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    app = workflow.compile()
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    
    result = app.invoke(state, {"configurable": {"thread_id": "1"}}, interrupt_after=["fetch_positions"])
    assert "Aave" in result["positions"]
    assert result["health_factor"] == 2.0

def test_3_analyze_sets_pending_actions(mock_llm, mock_get_positions):
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    app = workflow.compile()
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    
    result = app.invoke(state, {"configurable": {"thread_id": "2"}})
    assert len(result["pending_actions"]) > 0

def test_4_optimal_utilisation_skips_execution(mock_llm):
    def _mock_optimal(address):
        return {"_health_factor": 2.0, "_utilisation_rate": 60.0}
    
    mock_llm.invoke.return_value = AIMessage(content="NO_ACTION")
    workflow = create_agent_graph(mock_llm, [], _mock_optimal)
    
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer, interrupt_before=["execute"])
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    result = app.invoke(state, {"configurable": {"thread_id": "3"}})
    
    assert len(result["pending_actions"]) == 0

def test_5_circuit_breaker_health_factor(mock_llm):
    def _mock_low_hf(address):
        return {"_health_factor": 1.2, "_utilisation_rate": 80.0}
    
    workflow = create_agent_graph(mock_llm, [], _mock_low_hf)
    app = workflow.compile()
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    result = app.invoke(state, {"configurable": {"thread_id": "4"}})
    
    assert result["error"] == "circuit_breaker_health_factor"
    assert len(result["pending_actions"]) == 0

def test_6_thread_state_persists(mock_llm, mock_get_positions):
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    config = {"configurable": {"thread_id": "5"}}
    app.invoke(state, config)
    
    saved_state = app.get_state(config)
    assert saved_state is not None
    assert saved_state.values["user_address"] == "0x123"

def test_7_full_tick_completes_fast(mock_llm, mock_get_positions):
    import time
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    app = workflow.compile()
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    
    start = time.time()
    app.invoke(state, {"configurable": {"thread_id": "6"}})
    duration = time.time() - start
    
    assert duration < 30.0

def test_8_two_ticks_accumulate_state(mock_llm, mock_get_positions):
    workflow = create_agent_graph(mock_llm, [], mock_get_positions)
    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [], "error": ""}
    config = {"configurable": {"thread_id": "7"}}
    
    # First tick
    app.invoke(state, config)
    
    # Second tick
    mock_llm.invoke.return_value = AIMessage(content="MOCK_ACTION_2")
    app.invoke({"messages": [HumanMessage(content="Next tick")]}, config)
    
    saved_state = app.get_state(config).values
    assert len(saved_state["pending_actions"]) > 1
