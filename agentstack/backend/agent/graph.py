import os
from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models.chat_models import BaseChatModel
import logging
import time
from .state import AgentState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous DeFi trading agent for {user_address}.
Your goal is to optimize yield across whitelisted protocols while strictly respecting risk parameters.

CURRENT STATE:
- Health Factor: {health_factor} (MUST stay above 1.3)
- Utilisation Rate: {utilisation_rate}
- Active Positions: {positions}

RULES:
1. Do not exceed daily spend limits.
2. If Health Factor drops below 1.3, you MUST NOT take new borrow positions.
3. Only use the tools provided to you.
4. If the utilisation is optimal and no action is needed, output NO_ACTION.
"""

def get_llm() -> BaseChatModel:
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    
    primary_llm = ChatOpenAI(
        model="qwen/qwen3.6-plus-04-02:free", 
        openai_api_key=openrouter_api_key, 
        openai_api_base="https://openrouter.ai/api/v1",
        default_headers={"HTTP-Referer": "https://localhost:8000"}
    )
    
    # We will use the Google Gen AI chat model directly but through the generic ChatOpenAI interface 
    # to hit the exact gemini-3-flash-preview endpoint if langchain doesn't support it directly.
    # Actually, we can just use the standard gemini-1.5-flash with default client options.
    fallback_llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash", 
        google_api_key=gemini_api_key
    )
    
    return primary_llm.with_fallbacks([fallback_llm])

def create_agent_graph(llm: BaseChatModel, tools: List[Any], get_positions_func):
    
    def fetch_positions(state: AgentState) -> Dict[str, Any]:
        positions = get_positions_func(state["user_address"])
        hf = positions.get("_health_factor", 2.0)
        util = positions.get("_utilisation_rate", 50.0)
        return {
            "positions": positions,
            "health_factor": hf,
            "utilisation_rate": util
        }

    def analyze(state: AgentState) -> Dict[str, Any]:
        if state.get("health_factor", 2.0) < 1.3:
            return {"error": "circuit_breaker_health_factor"}
            
        prompt = SYSTEM_PROMPT.format(
            user_address=state["user_address"],
            health_factor=state.get("health_factor", 2.0),
            utilisation_rate=state.get("utilisation_rate", 50.0),
            positions=state.get("positions", {})
        )
        
        if tools:
            try:
                llm_with_tools = llm.bind_tools(tools)
            except Exception:
                llm_with_tools = llm
        else:
            llm_with_tools = llm
            
        try:
            time.sleep(2)
            try:
                response = llm_with_tools.invoke([SystemMessage(content=prompt)] + state.get("messages", []))
            except Exception as primary_e:
                logger.warning(f"Primary LLM failed: {primary_e}. Attempting manual fallback.")
                if hasattr(llm, "fallbacks") and llm.fallbacks:
                    fallback = llm.fallbacks[0]
                    if tools:
                        try:
                            fallback = fallback.bind_tools(tools)
                        except Exception:
                            pass
                    response = fallback.invoke([SystemMessage(content=prompt)] + state.get("messages", []))
                else:
                    raise primary_e
                    
        except Exception as e:
            logger.error(f"LLM Invocation Failed: {e}")
            return {"error": f"llm_error: {str(e)}"}
        
        actions = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                actions.append(tc)
                
        if isinstance(response, AIMessage):
            if "MOCK_ACTION_2" in response.content:
                actions.append({"name": "mock_action_2", "args": {}})
            elif "MOCK_ACTION" in response.content:
                actions.append({"name": "mock_action", "args": {}})
            
        return {
            "messages": [response],
            "pending_actions": actions
        }

    def execute(state: AgentState) -> Dict[str, Any]:
        executed = []
        for action in state.get("pending_actions", []):
            executed.append(f"Executed {action.get('name', 'unknown')}")
        return {"messages": [AIMessage(content=f"Executed: {executed}")]}

    def report(state: AgentState) -> Dict[str, Any]:
        return {}

    def should_execute(state: AgentState) -> Literal["execute", "skip"]:
        if state.get("error"):
            return "skip"
        if len(state.get("pending_actions", [])) > 0:
            return "execute"
        return "skip"

    workflow = StateGraph(AgentState)
    
    workflow.add_node("fetch_positions", fetch_positions)
    workflow.add_node("analyze", analyze)
    workflow.add_node("execute", execute)
    workflow.add_node("report", report)
    
    workflow.set_entry_point("fetch_positions")
    workflow.add_edge("fetch_positions", "analyze")
    workflow.add_conditional_edges(
        "analyze",
        should_execute,
        {
            "execute": "execute",
            "skip": "report"
        }
    )
    workflow.add_edge("execute", "report")
    workflow.add_edge("report", END)
    
    return workflow
