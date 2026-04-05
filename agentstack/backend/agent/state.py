from typing import TypedDict, List, Dict, Any, Annotated
import operator

def merge_lists(a: List[Any], b: List[Any]) -> List[Any]:
    if a is None:
        a = []
    if b is None:
        b = []
    return a + b

class AgentState(TypedDict):
    user_address: str
    positions: Dict[str, Any]
    # For testing, we want pending_actions to accumulate correctly over ticks
    pending_actions: Annotated[List[Dict[str, Any]], merge_lists]
    health_factor: float
    utilisation_rate: float
    messages: Annotated[List[Any], operator.add]
    error: str
