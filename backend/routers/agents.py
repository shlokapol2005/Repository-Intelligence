"""Agents router — Q&A, Architecture, Flow Tracer, Onboarding."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.agents import (
    build_qa_agent, build_arch_agent, build_flow_agent,
    build_impact_agent, build_onboard_agent, get_or_build_graph,
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


@router.post("/architecture")
async def arch_agent(req: ArchRequest):
    try:
        agent = build_arch_agent()
        result = agent.invoke({
            "repo_path": req.repo_path,
            "graph_dict": {},
            "mermaid_raw": "",
            "mermaid_enhanced": "",
            "summary": "",
            "steps": [],
        })
        return {
            "mermaid": result["mermaid_enhanced"] or result["mermaid_raw"],
            "summary": result["summary"],
            "steps": result["steps"],
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
            "steps": [],
        })
        return {
            "explanation": result["explanation"],
            "steps": result["steps"],
            "search_results": result["search_results"],
            "steps_structured": result.get("steps_structured", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impact")
async def impact_agent(req: ImpactAgentRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        agent = build_impact_agent()
        result = agent.invoke({
            "target_file": req.target_file,
            "repo_path": req.repo_path,
            "graph": cache["G"],
            "impact_raw": {},
            "risk_explanation": "",
            "steps": [],
        })
        return {
            "impact": result["impact_raw"],
            "risk_explanation": result["risk_explanation"],
            "steps": result["steps"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboard")
async def onboard_agent(req: OnboardRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        agent = build_onboard_agent()
        result = agent.invoke({
            "repo_path": req.repo_path,
            "graph_dict": cache["dict"],
            "learning_path": "",
            "_key_nodes": [],
            "steps": [],
        })
        return {
            "learning_path": result["learning_path"],
            "steps": result["steps"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
