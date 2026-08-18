import json
from typing import List, Dict, Any, Optional

class TaskPlan:
    def __init__(self, goal: str):
        self.goal = goal
        self.steps: List[Dict[str, Any]] = []
        self.current_step_index: int = 0
        self.status: str = "pending"  # pending, running, completed, failed, paused

    def add_step(self, thought: str, action: str, params: Dict[str, Any], target_label: str = ""):
        step_obj = {
            "step": len(self.steps) + 1,
            "thought": thought,
            "action": action,
            "params": params,
            "target_label": target_label,
            "status": "pending",
            "result": None,
            "annotation_img": None
        }
        self.steps.append(step_obj)
        return step_obj

    def mark_step_done(self, index: int, result: Any, annotation_img: Optional[str] = None):
        if 0 <= index < len(self.steps):
            self.steps[index]["status"] = "success"
            self.steps[index]["result"] = result
            if annotation_img:
                self.steps[index]["annotation_img"] = annotation_img

    def mark_step_failed(self, index: int, error_msg: str):
        if 0 <= index < len(self.steps):
            self.steps[index]["status"] = "error"
            self.steps[index]["error"] = error_msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "current_step_index": self.current_step_index,
            "total_steps": len(self.steps),
            "steps": self.steps
        }
