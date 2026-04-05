from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseSkill(ABC):
    SKILL_ID: int
    
    @abstractmethod
    def get_tools(self) -> List[Any]:
        pass
        
    @abstractmethod
    def get_position_summary(self, user_address: str) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def health_check(self) -> bool:
        pass
