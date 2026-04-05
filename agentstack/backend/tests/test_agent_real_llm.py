import pytest
import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agent.graph import create_agent_graph
from langgraph.checkpoint.memory import MemorySaver
import logging

logging.basicConfig(level=logging.INFO)

# Ensure env vars are set
os.environ["OPENROUTER_API_KEY"] = "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"
os.environ["GOOGLE_API_KEY"] = "AIzaSyD1nqNngiQ5utdl1eDq1RX8P_bjP693B5A"

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

def test_real_llm_invocation_gemini_fallback():
    broken_llm = ChatOpenAI(
        model="qwen/qwen3.6-plus-04-02:free", 
        api_key="sk-or-v1-brokenkey", 
        base_url="https://localhost:9999/api/v1", 
        max_retries=0
    )
    
    # Use standard 1.5 flash which was failing before due to client_options dict issue
    gemini_llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.environ["GOOGLE_API_KEY"]
    )
    
    fallback_llm = broken_llm.with_fallbacks([gemini_llm])
    
    workflow = create_agent_graph(fallback_llm, [], mock_get_positions)
    app = workflow.compile()
    
    state = {"user_address": "0x123", "positions": {}, "pending_actions": [], "health_factor": 0.0, "utilisation_rate": 0.0, "messages": [HumanMessage(content="Explain how AI works in 5 words.")], "error": ""}
    
    result = app.invoke(state, {"configurable": {"thread_id": "real_2"}})
    
    assert "error" not in result or not result["error"]
    assert len(result["messages"]) > 0
    
    last_message = result["messages"][-1]
    print("Gemini Output:", last_message.content)
    assert len(last_message.content) > 0
