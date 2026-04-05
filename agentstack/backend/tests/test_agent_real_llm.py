import pytest
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from agent.graph import create_agent_graph
from langgraph.checkpoint.memory import MemorySaver
import logging

logging.basicConfig(level=logging.INFO)

# Ensure env vars are set
os.environ["OPENROUTER_API_KEY"] = "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"

def mock_get_positions(address):
    return {
        "Aave": {"supplied": 1000},
        "_health_factor": 2.0,
        "_utilisation_rate": 50.0
    }

def test_real_llm_invocation_openrouter():
    llm = ChatOpenAI(
        model="qwen/qwen3.6-plus-04-02:free", 
        api_key=os.environ["OPENROUTER_API_KEY"], 
        base_url="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://localhost:8000"},
        model_kwargs={"reasoning": {"enabled": True}}
    )
    
    workflow = create_agent_graph(llm, [], mock_get_positions)
    app = workflow.compile()
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [HumanMessage(content="Explain how AI works in 5 words.")], "error": ""}
    
    result = app.invoke(state, {"configurable": {"thread_id": "real_1"}})
    
    assert "error" not in result or not result["error"]
    assert len(result["messages"]) > 0
    
    last_message = result["messages"][-1]
    print("OpenRouter Output:", last_message.content)
    assert len(last_message.content) > 0

