"""
Agent Manifest — Core Protocol for Agent-Factory

This module defines the *interface contract* that all agents must obey.
It is not a tool — it is the *self-consistent grammar of agency*.

Principle: Agent = Code + Config + Contract
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================================
# Manifest Core — The Universal Schema
# ============================================================================

@dataclass(frozen=True)
class AgentManifest:
    """
    Every agent — including Ouroboros itself — has this manifest.
    Not optional. Not "optional config". This is the *grammar of agency*.
    """
    name: str  # unique identifier, e.g., "agent-reference-v1"
    version: str  # semver
    type: str  # "reference" | "architect" | "coder" | "tester" | "deployer"
    description: str  # human-readable purpose

    state_machine: str  # e.g., "event_loop", "react_agent", "chain_of_thought"
    event_loop: Dict[str, Any]  # schema: { triggers: [...], handlers: {...} }
    api: Dict[str, Any]  # e.g., {"type": "fastapi", "endpoints": [...], "auth": null}

    # ——— Sacred constraints ———
    memory: Dict[str, bool]  # e.g., {"scratchpad": true, "identity": false}
    logging: Dict[str, Any]  # e.g., {"traceability": "full", "retention_days": 30}
    deployment: Dict[str, Any]  # e.g., {"type": "distroless-container", "self_test": true}

    # ——— Self-attestation ———
    self_test: bool  # MUST pass before deployment
    security_review: bool  # MUST pass (no secrets, no arbitrary code exec)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentManifest":
        """Parse manifest from raw dict (JSON/YAML)."""
        return cls(
            name=data["name"],
            version=data["version"],
            type=data["type"],
            description=data["description"],
            state_machine=data["state_machine"],
            event_loop=data["event_loop"],
            api=data["api"],
            memory=data["memory"],
            logging=data["logging"],
            deployment=data["deployment"],
            self_test=data.get("self_test", True),
            security_review=data.get("security_review", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize manifest for storage."""
        return {
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "description": self.description,
            "state_machine": self.state_machine,
            "event_loop": self.event_loop,
            "api": self.api,
            "memory": self.memory,
            "logging": self.logging,
            "deployment": self.deployment,
            "self_test": self.self_test,
            "security_review": self.security_review,
        }

    def save(self, path: pathlib.Path) -> None:
        """Save manifest as `agent.yaml` + `manifest.json`."""
        path.parent.mkdir(parents=True, exist_ok=True)

        # YAML (human-readable)
        yaml_path = path.with_suffix(".yaml")
        import yaml
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, default_flow_style=False)

        # JSON (machine-readable)
        json_path = path.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: pathlib.Path) -> "AgentManifest":
        """Load manifest from file (YAML or JSON)."""
        if path.suffix == ".yaml":
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        elif path.suffix == ".json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            raise ValueError(f"Unknown manifest format: {path.suffix}")

        return cls.from_dict(data)


# ============================================================================
# Reference Agent — Finds Similar Agents
# ============================================================================

@dataclass(frozen=True)
class ReferenceAgentOutput:
    """Result of Research Agent: list of patterns + new agent design draft."""
    search_query: str
    github_repos: List[Dict[str, Any]]  # e.g., {"name": "swe-agent", "stars": 123, "url": "..."}
    npm_packages: List[Dict[str, Any]]
    github_apps: List[Dict[str, Any]]
    patterns_extracted: List[str]  # e.g., ["react_agent", "event_loop", "self-test-first"]
    draft_design: Dict[str, Any]  # e.g., {"state_machine": "react", "api_endpoints": ["/execute"]}

    def to_manifest(self, name: str, version: str) -> AgentManifest:
        """Convert draft design to full manifest."""
        return AgentManifest(
            name=name,
            version=version,
            type="reference",
            description=f"Agent generated by Research Agent (v{version}) based on {len(self.patterns_extracted)} patterns",
            state_machine=self.draft_design.get("state_machine", "event_loop"),
            event_loop={
                "triggers": [self.draft_design.get("trigger", "message")],
                "handlers": self.draft_design.get("handlers", {}),
            },
            api={
                "type": "fastapi",
                "endpoints": self.draft_design.get("api_endpoints", ["/execute"]),
            },
            memory={"scratchpad": True, "identity": False},
            logging={"traceability": "full", "retention_days": 30},
            deployment={"type": "distroless-container", "self_test": True},
            self_test=True,
            security_review=True,
        )


# ============================================================================
# Architect Agent — Design Structure
# ============================================================================

@dataclass(frozen=True)
class ArchitectAgentOutput:
    """Result of Agent Architect: state machine + event loop schema."""
    agent_type: str
    problem_description: str
    state_machine_schema: Dict[str, Any]  # e.g., {"states": [...], "transitions": {...}}
    event_loop_schema: Dict[str, Any]
    api_interface: List[Dict[str, Any]]  # [{"method": "POST", "path": "/execute", "schema": {...}}]

    def validate(self) -> bool:
        """Check: state machine is acyclic, event loop has handler for every trigger."""
        states = self.state_machine_schema.get("states", [])
        transitions = self.state_machine_schema.get("transitions", [])

        # Rule 1: No self-loops in transitions (unless explicit "loop" state)
        for t in transitions:
            if t.get("from") == t.get("to") and t.get("trigger") != "loop":
                raise ValueError(f"Invalid self-loop in transition: {t}")

        # Rule 2: Every trigger has handler
        triggers = set(self.event_loop_schema.get("triggers", []))
        handlers = set(self.event_loop_schema.get("handlers", {}).keys())
        missing = triggers - handlers
        if missing:
            raise ValueError(f"Missing event loop handlers for triggers: {missing}")

        return True


# ============================================================================
# Coder Agent — Generate Code
# ============================================================================

@dataclass(frozen=True)
class GeneratedFile:
    """One file generated for new agent."""
    path: str  # e.g., "src/main.py"
    content: str
    language: str  # "python", "javascript", etc.
    type: str  # "code", "config", "dockerfile", "manifest"

    def validate(self) -> bool:
        """Basic sanity checks."""
        if not self.content or len(self.content.strip()) == 0:
            raise ValueError(f"Empty file: {self.path}")
        if self.path.startswith("..") or self.path.startswith("/"):
            raise ValueError(f"Path traversal attempt: {self.path}")
        return True


@dataclass(frozen=True)
class CoderAgentOutput:
    """Result of Agent Coder: list of files + deployment config."""
    files: List[GeneratedFile]
    requirements_txt: str
    dockerfile: str

    def validate(self) -> bool:
        """Check: all files are safe, no secrets."""
        for f in self.files:
            f.validate()
            # Rule: No hardcoded secrets
            if "SECRET" in f.content.upper() or "API_KEY=" in f.content:
                raise ValueError(f"Potential secret found in: {f.path}")
        return True


# ============================================================================
# Tester Agent — Safety & Correctness
# ============================================================================

@dataclass(frozen=True)
class TestCase:
    """One test case."""
    id: str
    name: str
    input: Dict[str, Any]
    expected_output: Any
    actual_output: Optional[Any] = None
    passed: bool = False
    error_message: Optional[str] = None


@dataclass(frozen=True)
class TesterAgentOutput:
    """Result of Agent Tester: test report."""
    total_tests: int
    passed: int
    failed: int
    tests: List[TestCase]
    security_report: Dict[str, Any]  # e.g., {"secrets_found": 0, "arbitrary_code_exec": false}

    def to_summary(self) -> str:
        if self.failed == 0 and self.security_report.get("secrets_found", 0) == 0:
            return f"✅ All {self.total_tests} tests passed, no security issues"
        else:
            return f"❌ {self.failed}/{self.total_tests} tests failed, security issues found"


# ============================================================================
# Deployer Agent — PR + Cloud
# ============================================================================

@dataclass(frozen=True)
class DeploymentResult:
    """Result of Agent Deployer."""
    pr_url: Optional[str]
    deploy_url: Optional[str]
    commit_hash: str
    deployment_timestamp: str


# ============================================================================
# Factory Protocol — Orchestrates All Agents
# ============================================================================

class AgentFactoryProtocol:
    """
    The *grammar of agency*: how agents build agents.

    Lifecycle:
      1. Research Agent — find patterns
      2. Architect Agent — design structure
      3. Coder Agent — generate code
      4. Tester Agent — verify safety & correctness
      5. Deployer Agent — create PR + deploy

    No agent proceeds to next step without passing `self_test`.
    """

    def __init__(self, repo_dir: pathlib.Path):
        self.repo_dir = repo_dir
        self.agents_path = repo_dir / "agents"
        self.agents_path.mkdir(parents=True, exist_ok=True)

    def run_cycle(
        self,
        user_task: str,
        reference_agents: List[Dict[str, Any]] = None,
    ) -> DeploymentResult:
        """
        Full agent generation cycle.

        Return: final deployment result (PR + URL).
        """

        # Step 1: Research
        reference_output = self._run_reference_agent(user_task, reference_agents)

        # Step 2: Architect
        architect_output = self._run_architect_agent(user_task, reference_output)

        # Step 3: Coder
        coder_output = self._run_coder_agent(architect_output)

        # Step 4: Tester (MUST PASS before deploy)
        tester_output = self._run_tester_agent(coder_output, user_task)

        if not tester_output.passed == tester_output.total_tests:
            raise ValueError(f"Tests failed: {tester_output.to_summary()}")

        # Step 5: Deployer
        deploy_result = self._run_deployer_agent(coder_output, tester_output)

        return deploy_result

    def _run_reference_agent(self, task: str, existing_agents: List[Dict[str, Any]]) -> ReferenceAgentOutput:
        """Research Agent: find patterns."""
        # Placeholder — will be implemented in tools/
        raise NotImplementedError("Reference agent not yet implemented")

    def _run_architect_agent(self, task: str, reference: ReferenceAgentOutput) -> ArchitectAgentOutput:
        """Architect Agent: design structure."""
        raise NotImplementedError("Architect agent not yet implemented")

    def _run_coder_agent(self, arch: ArchitectAgentOutput) -> CoderAgentOutput:
        """Coder Agent: generate code."""
        raise NotImplementedError("Coder agent not yet implemented")

    def _run_tester_agent(self, code: CoderAgentOutput, task: str) -> TesterAgentOutput:
        """Tester Agent: verify safety & correctness."""
        raise NotImplementedError("Tester agent not yet implemented")

    def _run_deployer_agent(self, code: CoderAgentOutput, test_result: TesterAgentOutput) -> DeploymentResult:
        """Deployer Agent: PR + deploy."""
        raise NotImplementedError("Deployer agent not yet implemented")


# ============================================================================
# Self-Test Entry Point — `agent --self-test`
# ============================================================================

def self_test():
    """Entry point: `python -m ouroboros.agent_manifest --self-test`"""
    print("🧪 Running self-test for Agent Manifest Protocol...")

    # Test 1: Manifest round-trip
    m = AgentManifest(
        name="test-agent-v1",
        version="0.1.0",
        type="reference",
        description="Test agent",
        state_machine="event_loop",
        event_loop={"triggers": ["msg"], "handlers": {}},
        api={"type": "fastapi", "endpoints": ["/test"]},
        memory={"scratchpad": True, "identity": False},
        logging={"traceability": "full"},
        deployment={"type": "distroless-container", "self_test": True},
        self_test=True,
        security_review=True,
    )
    d = m.to_dict()
    m2 = AgentManifest.from_dict(d)
    assert m.name == m2.name, "Round-trip failed"

    print("✅ Manifest round-trip: OK")

    # Test 2: Files safe path check
    f = GeneratedFile(path="src/main.py", content="# test", language="python", type="code")
    assert f.validate() is True

    try:
        GeneratedFile(path="../etc/passwd", content="", language="text", type="config")
        assert False, "Path traversal should fail"
    except ValueError:
        print("✅ Path traversal prevention: OK")

    # Test 3: Secret detection
    try:
        f = GeneratedFile(path="main.py", content="API_KEY=sk-1234567890abcdef", language="python", type="code")
        f.validate()
        assert False, "Secret detection should fail"
    except ValueError:
        print("✅ Secret detection: OK")

    print("\n🎯 Agent Manifest Protocol self-test passed.")
    return True


if __name__ == "__main__":
    self_test()
