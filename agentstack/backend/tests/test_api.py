import pytest
from fastapi.testclient import TestClient
from main import app
from typing import Dict, Any
import os

# Mock the env var so OpenAI init doesn't fail
os.environ["OPENROUTER_API_KEY"] = "mock_key"

client = TestClient(app)

def test_1_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_2_cors_headers_present():
    response = client.options(
        "/health", 
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    # FastAPI CORS middleware reflects the origin back instead of '*' when credentials are true
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

def test_3_dashboard_auth_enforced():
    response = client.get("/api/dashboard")
    assert response.status_code == 400
    
    response = client.get("/api/dashboard", headers={"X-User-Address": "0x123"})
    assert response.status_code == 200
    assert response.json()["user_address"] == "0x123"

def test_4_websocket_accepts_connection():
    with client.websocket_connect("/ws/chat/0x123") as websocket:
        assert websocket is not None

def test_5_websocket_echo_and_langgraph():
    from unittest.mock import patch, MagicMock, AsyncMock
    from langchain_core.messages import AIMessage
    
    with patch("main.create_agent_graph") as mock_graph:
        # Mocking app to have an async method `ainvoke`
        mock_app = MagicMock()
        mock_app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Hello from agent!")]})
        
        mock_workflow = MagicMock()
        mock_workflow.compile.return_value = mock_app
        mock_graph.return_value = mock_workflow
        
        with client.websocket_connect("/ws/chat/0x456") as websocket:
            websocket.send_text("Hello")
            data = websocket.receive_text()
            assert data == "Hello from agent!"

def test_6_websocket_disconnect_handled_gracefully():
    from main import manager
    
    with client.websocket_connect("/ws/chat/0x789") as websocket:
        assert "0x789" in manager.active_connections
        
    assert "0x789" not in manager.active_connections
