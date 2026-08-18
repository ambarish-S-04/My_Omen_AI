import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Callable

from backend.config import config
from backend.core.safety import safety_guard
from backend.core.memory import memory_store
from backend.core.worker import WorkerAgent, WORKER_NAMES
from backend.core.phone_worker import phone_worker
from backend.core.agent import aether_agent
from backend.llm.openrouter_provider import openrouter_provider
from backend.llm import get_llm_provider
from backend.voice.interrupter import voice_interrupter
from backend.actions.direct_executor import direct_executor
from backend.actions.phone_executor import phone_executor


class Cortex:
    """
    CORTEX — The Multi-Agent Orchestration Brain of OMEN.
    
    Analyzes user prompts via Nemotron 550B (OpenRouter), determines optimal
    execution strategy (single vs parallel), spawns and manages worker agents,
    and reports progress at every step.
    """
    
    def __init__(self):
        self.active_workers: List[WorkerAgent] = []
        self.session_id: Optional[str] = None
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.is_running = False
    
    def set_broadcaster(self, cb: Callable[[Dict[str, Any]], Any]):
        self.broadcast_callback = cb
    
    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        if self.broadcast_callback:
            try:
                msg = {"event": event_type, "data": data, "timestamp": time.time()}
                res = self.broadcast_callback(msg)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[Cortex] Broadcast error: {e}")
    
    async def analyze_and_plan(self, user_prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send user prompt to Nemotron 550B for task decomposition."""
        await self.broadcast("cortex_status", {"status": "ANALYZING", "prompt": user_prompt})
        plan = await openrouter_provider.analyze_task(user_prompt, context=context)
        await self.broadcast("cortex_plan", {"plan": plan})
        return plan
    
    async def execute(self, user_prompt: str, context: Optional[Dict[str, Any]] = None, 
                      dry_run: bool = False) -> Dict[str, Any]:
        """
        Full orchestration pipeline:
        1. Analyze prompt via Cortex (Nemotron 550B)
        2. Decide single vs parallel
        3. Spawn workers and execute
        4. Report at every step
        5. Synthesize final results
        """
        self.session_id = str(uuid.uuid4())[:8]
        self.is_running = True
        self.active_workers = []
        safety_guard.reset()
        
        # Start voice interruption listener for the entire orchestration session
        voice_interrupter.start(on_interrupt=lambda text: self._handle_voice_interrupt(text))
        
        try:
            # Step 1: Cortex Analysis
            await self.broadcast("cortex_status", {"status": "ANALYZING", "prompt": user_prompt})
            plan = await openrouter_provider.analyze_task(user_prompt, context=context)
            
            strategy = plan.get("strategy", "single")
            subtasks = plan.get("subtasks", [])
            reasoning = plan.get("reasoning", "")
            chat_response = plan.get("chat_response", "")
            
            await self.broadcast("cortex_plan", {
                "strategy": strategy,
                "subtasks": subtasks,
                "reasoning": reasoning,
                "estimated_complexity": plan.get("estimated_complexity", "medium")
            })
            
            # Handle CHAT intent
            if strategy == "chat":
                self.is_running = False
                voice_interrupter.stop()
                return {
                    "session_id": self.session_id,
                    "strategy": "chat",
                    "response": chat_response,
                    "status": "completed"
                }
            
            # If no subtasks, fallback
            if not subtasks:
                subtasks = [{"id": "A", "goal": user_prompt, "type": "ui_action", "depends_on": [], "priority": 1}]
            
            # Step 2: Execute based on strategy
            # Try DIRECT EXECUTION first (instant), fallback to vision if needed
            if strategy == "single" or len(subtasks) == 1:
                results = await self._execute_single(subtasks[0], dry_run)
            else:
                results = await self._execute_parallel(subtasks, dry_run)
            
            # Step 3: Synthesize results
            if len(results) > 1:
                await self.broadcast("cortex_status", {"status": "SYNTHESIZING"})
                summary = await openrouter_provider.synthesize_results(user_prompt, results)
            else:
                summary = results[0].get("summary", "Task completed.") if results else "No results."
            
            # Save orchestration log
            memory_store.save_orchestration_log(
                session_id=self.session_id,
                strategy=strategy,
                subtasks=subtasks,
                results=results,
                total_workers=len(results)
            )
            
            await self.broadcast("cortex_completed", {
                "session_id": self.session_id,
                "summary": summary,
                "total_workers": len(results),
                "strategy": strategy,
                "results": [{
                    "worker": r.get("worker_name", "?"),
                    "goal": r.get("goal", "?"),
                    "status": r.get("status", "?"),
                    "steps": r.get("total_steps", 0)
                } for r in results]
            })
            
            return {
                "session_id": self.session_id,
                "strategy": strategy,
                "summary": summary,
                "results": results,
                "status": "completed"
            }
        
        except Exception as e:
            print(f"[Cortex] Error: {e}")
            await self.broadcast("cortex_status", {"status": "ERROR", "error": str(e)})
            return {
                "session_id": self.session_id,
                "strategy": "error",
                "summary": f"Cortex error: {e}",
                "results": [],
                "status": "error"
            }
        
        finally:
            voice_interrupter.stop()
            self.is_running = False
            self.active_workers = []
    
    async def _execute_single(self, subtask: Dict[str, Any], dry_run: bool) -> List[Dict[str, Any]]:
        """Execute a single subtask: Direct Execution first, Vision fallback if needed."""
        goal = subtask.get("goal", "")
        task_type = subtask.get("type", "ui_action")
        
        is_phone = task_type == "phone_action" or "phone" in goal.lower() or "mobile" in goal.lower()
        target = "phone" if is_phone else "pc"
        
        # ── PHASE 1: Try Direct Execution (instant, 200ms) ──
        await self.broadcast("cortex_status", {"status": "GENERATING_COMMANDS", "mode": "DIRECT", "target": target, "goal": goal})
        
        llm = get_llm_provider()
        cmd_plan = await llm.generate_commands(goal=goal, target=target)
        method = cmd_plan.get("method", "direct")
        commands = cmd_plan.get("commands", [])
        explanation = cmd_plan.get("explanation", "")
        
        if method == "direct" and commands:
            # Direct execution path — no screenshots, no vision!
            return await self._execute_direct(goal, commands, explanation, target, dry_run)
        
        # ── PHASE 2: Vision Fallback (when LLM says vision_needed or no commands) ──
        await self.broadcast("cortex_status", {"status": "DISPATCHING", "mode": "VISION_FALLBACK", "goal": goal})
        
        if is_phone:
            phone_worker.set_broadcaster(self.broadcast_callback)
            result = await phone_worker.run_task(goal=goal, dry_run=dry_run)
            return [result]
        else:
            aether_agent.set_broadcaster(self.broadcast_callback)
            result = await aether_agent.run_task(goal=goal, dry_run=dry_run, voice_enabled=False)
            return [{
                "worker_id": "PRIMARY",
                "worker_name": "PRIMARY",
                "goal": goal,
                "status": result.get("status", "unknown"),
                "summary": result.get("summary", ""),
                "total_steps": len(result.get("steps", [])),
                "steps": result.get("steps", [])
            }]
    
    async def _execute_direct(self, goal: str, commands: List[Dict[str, Any]], 
                               explanation: str, target: str, dry_run: bool) -> List[Dict[str, Any]]:
        """Execute a sequence of direct commands (no vision needed)."""
        executor = phone_executor if target == "phone" else direct_executor
        steps = []
        all_ok = True
        
        await self.broadcast("direct_execution_start", {
            "goal": goal,
            "target": target,
            "total_commands": len(commands),
            "explanation": explanation
        })
        
        for i, cmd in enumerate(commands):
            if safety_guard.is_stopped:
                await self.broadcast("direct_execution_step", {"step": i+1, "status": "STOPPED", "tool": cmd.get("tool")})
                break
            
            tool = cmd.get("tool", "")
            params = cmd.get("params", {})
            
            await self.broadcast("direct_execution_step", {
                "step": i+1,
                "total": len(commands),
                "tool": tool,
                "params": params,
                "status": "EXECUTING"
            })
            
            if dry_run:
                result = {"status": "dry_run", "tool": tool, "params": params}
            else:
                result = executor.execute_command(tool, params)
            
            step_ok = result.get("status") in ["success", "dry_run"]
            if not step_ok:
                all_ok = False
            
            steps.append({
                "step": i+1,
                "tool": tool,
                "params": params,
                "result": result,
                "status": "done" if step_ok else "error"
            })
            
            await self.broadcast("direct_execution_step", {
                "step": i+1,
                "total": len(commands),
                "tool": tool,
                "status": "DONE" if step_ok else "ERROR",
                "result_summary": str(result.get("status", "")) + " " + str(result.get("message", result.get("output", "")))[:100]
            })
            
            # Small delay between commands
            if i < len(commands) - 1:
                await asyncio.sleep(0.3)
        
        final_status = "completed" if all_ok else "partial"
        summary = f"{'✅' if all_ok else '⚠️'} {explanation} ({len(steps)} commands executed via direct execution)"
        
        return [{
            "worker_id": "DIRECT",
            "worker_name": "⚡ DIRECT",
            "goal": goal,
            "status": final_status,
            "summary": summary,
            "total_steps": len(steps),
            "steps": steps
        }]
    
    async def _execute_parallel(self, subtasks: List[Dict[str, Any]], dry_run: bool) -> List[Dict[str, Any]]:
        """Execute multiple subtasks using parallel WorkerAgents."""
        # Build dependency graph
        dep_graph = {}
        for st in subtasks:
            dep_graph[st["id"]] = st.get("depends_on", [])
        
        # Separate independent and dependent tasks
        independent = [st for st in subtasks if not st.get("depends_on")]
        dependent = [st for st in subtasks if st.get("depends_on")]
        
        all_results = []
        completed_ids = set()
        
        await self.broadcast("cortex_status", {
            "status": "DISPATCHING", 
            "mode": "PARALLEL",
            "total_agents": len(subtasks),
            "independent": len(independent),
            "dependent": len(dependent)
        })
        
        # Phase 1: Execute all independent tasks in parallel
        if independent:
            phase1_results = await self._run_workers_parallel(independent, dry_run)
            all_results.extend(phase1_results)
            for st in independent:
                completed_ids.add(st["id"])
        
        # Phase 2: Execute dependent tasks (in order of dependency resolution)
        remaining = list(dependent)
        max_rounds = 5  # prevent infinite loops
        round_count = 0
        
        while remaining and round_count < max_rounds:
            round_count += 1
            ready = [st for st in remaining if all(d in completed_ids for d in st.get("depends_on", []))]
            
            if not ready:
                # Deadlock — force execute remaining
                ready = remaining
            
            phase_results = await self._run_workers_parallel(ready, dry_run)
            all_results.extend(phase_results)
            
            for st in ready:
                completed_ids.add(st["id"])
                remaining.remove(st)
        
        return all_results
    
    async def _run_workers_parallel(self, subtasks: List[Dict[str, Any]], dry_run: bool) -> List[Dict[str, Any]]:
        """Spawn and run multiple workers in parallel (with concurrency cap)."""
        tasks = []
        worker_records = []
        
        for i, st in enumerate(subtasks[:config.MAX_PARALLEL_AGENTS]):
            task_type = st.get("type", "ui_action")
            goal = st.get("goal", "")
            is_phone = task_type == "phone_action" or "phone" in goal.lower() or "mobile" in goal.lower()
            
            if is_phone:
                worker_name = "PHONE"
                phone_worker.set_broadcaster(self.broadcast_callback)
                tasks.append(phone_worker.run_task(goal=goal, dry_run=dry_run))
                worker_records.append({"worker_id": "PHONE", "worker_name": "PHONE", "goal": goal})
                
                await self.broadcast("cortex_worker_spawned", {
                    "worker_name": "PHONE",
                    "goal": goal,
                    "task_type": "phone_action"
                })
            else:
                worker_name = WORKER_NAMES[i] if i < len(WORKER_NAMES) else f"WORKER-{i+1}"
                worker_id = f"{self.session_id}-{worker_name}"
                
                worker = WorkerAgent(worker_id=worker_id, worker_name=worker_name)
                worker.set_broadcaster(self.broadcast_callback)
                self.active_workers.append(worker)
                tasks.append(worker.run_task(goal=goal, task_type=task_type, dry_run=dry_run))
                worker_records.append({"worker_id": worker_id, "worker_name": worker_name, "goal": goal})
                
                await self.broadcast("cortex_worker_spawned", {
                    "worker_name": worker_name,
                    "goal": goal,
                    "task_type": task_type
                })
        
        # Run all workers concurrently
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append({
                    "worker_id": workers[i].worker_id,
                    "worker_name": workers[i].worker_name,
                    "goal": subtasks[i].get("goal", ""),
                    "status": "error",
                    "summary": str(result),
                    "total_steps": 0,
                    "steps": []
                })
            else:
                processed.append(result)
        
        return processed
    
    def _handle_voice_interrupt(self, spoken_text: str):
        """Handle voice interrupt — stop all active workers."""
        for worker in self.active_workers:
            worker.is_running = False
        self.is_running = False
    
    def stop_all(self, reason: str = "User stopped all agents"):
        """Emergency stop all workers and the cortex."""
        safety_guard.trigger_emergency_stop(reason)
        for worker in self.active_workers:
            worker.is_running = False
        self.is_running = False


# Singleton
cortex = Cortex()
