"""AI Features router — Agents (Q&A, Flow) + Pipelines (Architecture, Impact, Onboard)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.agents import (
    build_qa_agent, build_flow_agent,
    generate_architecture, run_impact_analysis, generate_onboarding,
    get_or_build_graph,
)

router = APIRouter()


class QARequest(BaseModel):
    question: str
    repo_path: str
    index_name: str


class ArchRequest(BaseModel):
    repo_path: str


class FlowRequest(BaseModel):
    feature: str
    repo_path: str
    index_name: str


class ImpactAgentRequest(BaseModel):
    target_file: str
    repo_path: str


class OnboardRequest(BaseModel):
    repo_path: str


# ── Agent endpoints (LangGraph) ─────────────────────────────────────────────

@router.post("/qa")
async def qa_agent(req: QARequest):
    try:
        agent = build_qa_agent()
        result = agent.invoke({
            "question": req.question,
            "repo_path": req.repo_path,
            "index_name": req.index_name,
            "retrieved_chunks": [],
            "file_contents": [],
            "answer": "",
            "confidence_ok": True,
            "steps": [],
        })
        return {
            "answer": result["answer"],
            "steps": result["steps"],
            "sources": list({c["file"] for c in result["retrieved_chunks"]}),
            "confidence_ok": result.get("confidence_ok", True),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flow")
async def flow_agent(req: FlowRequest):
    try:
        agent = build_flow_agent()
        result = agent.invoke({
            "feature": req.feature,
            "repo_path": req.repo_path,
            "index_name": req.index_name,
            "search_results": [],
            "flow_trace": [],
            "steps_structured": [],
            "graph_edges": [],
            "explanation": "",
            "disclaimer": "",
            "steps": [],
        })
        return {
            "explanation": result["explanation"],
            "steps": result["steps"],
            "search_results": result["search_results"],
            "steps_structured": result.get("steps_structured", []),
            "disclaimer": result.get("disclaimer", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pipeline endpoints (plain functions) ─────────────────────────────────────

@router.post("/architecture")
async def arch_pipeline(req: ArchRequest):
    try:
        result = generate_architecture(req.repo_path)
        return {
            "mermaid": result["mermaid"],
            "summary": result["summary"],
            "steps": result["steps"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impact")
async def impact_pipeline(req: ImpactAgentRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        result = run_impact_analysis(cache["G"], req.target_file)
        return {
            "impact": result["impact"],
            "risk_explanation": result["risk_explanation"],
            "steps": result["steps"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboard")
async def onboard_pipeline(req: OnboardRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        result = generate_onboarding(cache["dict"])
        return {
            "learning_path": result["learning_path"],
            "steps": result["steps"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
