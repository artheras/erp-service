"""Dependency-free agent and team runtime primitives for erp-service."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class SignalScheme:
    name: str
    levels: tuple[str, ...]
    default_level: str = "WATCH"

    def vote(self, results: List["AgentResult"]) -> tuple[str, float]:
        if not results:
            return self.default_level, 0.0
        severity = {lvl: idx for idx, lvl in enumerate(self.levels)}
        worst = max(results, key=lambda r: severity.get(r.signal, 1))
        avg_conf = round(sum(r.confidence for r in results) / len(results), 4)
        return worst.signal, avg_conf


WAREHOUSE_SCHEME = SignalScheme(
    name="warehouse",
    levels=("GOOD", "WATCH", "CONCERN", "SEVERE"),
    default_level="WATCH",
)


@dataclass
class AgentResult:
    agent: str
    symbol: str
    analysis: str
    confidence: float = 0.5
    signal: str = "WATCH"
    key_points: List[str] = field(default_factory=list)
    data_used: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    provenance: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TeamResult:
    symbol: str
    results: List[AgentResult]
    final_signal: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_signal": self.final_signal,
            "confidence": self.confidence,
            "results": [item.to_dict() for item in self.results],
        }


class BaseAgent:
    name: str = "base"
    description: str = ""

    def __init__(
        self,
        llm_provider: Any = None,
        data_router: Any = None,
        on_token: Optional[Callable[[str], None]] = None,
        on_thought: Optional[Callable[[str], None]] = None,
        on_tool_start: Optional[Callable[[str, Dict], None]] = None,
        on_tool_end: Optional[Callable[[str, Any], None]] = None,
        lang: str = "zh",
    ) -> None:
        self.llm_provider = llm_provider
        self.data_router = data_router
        self.on_token = on_token
        self.on_thought = on_thought
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.lang = lang

    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        raise NotImplementedError(f"Unknown tool: {tool_name}")

    async def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentResult:
        raise NotImplementedError


class AgentTeam:
    def __init__(
        self,
        signal_scheme: SignalScheme = WAREHOUSE_SCHEME,
        on_agent_done: Optional[Callable[[str, AgentResult], None]] = None,
        timeout_per_agent: float = 20.0,
    ) -> None:
        self.signal_scheme = signal_scheme
        self.on_agent_done = on_agent_done
        self.timeout_per_agent = timeout_per_agent

    async def run(
        self,
        symbol: str,
        agents: List[str],
        agent_data: Dict[str, Dict[str, Any]],
    ) -> TeamResult:
        from erp_service.agents import AGENT_CLASSES

        async def _run_one(name: str) -> AgentResult:
            cls = AGENT_CLASSES[name]
            agent = cls()
            res = await asyncio.wait_for(
                agent.analyze(symbol, agent_data.get(name, {})),
                timeout=self.timeout_per_agent,
            )
            if self.on_agent_done:
                self.on_agent_done(name, res)
            return res

        results = list(await asyncio.gather(*(_run_one(name) for name in agents)))
        severity = {lvl: idx for idx, lvl in enumerate(self.signal_scheme.levels)}
        worst = max(
            results,
            key=lambda r: severity.get(r.signal, 1),
            default=None,
        )
        final_signal = worst.signal if worst else self.signal_scheme.default_level
        avg_conf = (
            sum(r.confidence for r in results) / len(results) if results else 0.0
        )
        return TeamResult(
            symbol=symbol,
            results=results,
            final_signal=final_signal,
            confidence=round(avg_conf, 4),
        )
