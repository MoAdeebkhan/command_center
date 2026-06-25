"""
FastAPI application — Agentic BI Migration Platform
Endpoints:
  POST /api/jobs            — upload file, start pipeline
  GET  /api/jobs            — list all jobs
  GET  /api/jobs/{id}       — get job detail + agent steps
  POST /api/jobs/{id}/approve — HITL approve
  POST /api/jobs/{id}/reject  — HITL reject
  GET  /api/jobs/{id}/download — download migration output
  GET  /api/ollama/status   — check Ollama connectivity
  GET  /health              — health check
"""
import json
import uuid
import logging
import threading
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from database import get_db, init_db
from pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic BI Migration Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

AGENT_NAMES = [
    "Reader Agent",
    "Business Logic Agent",
    "Extraction Agent",
    "Conversion Agent",
    "Documentation Agent",
    "Validation Agent",
    "Deployment Agent",
]

OLLAMA_HOST = "http://10.10.0.130:11434"
OLLAMA_MODEL = "llama3:latest"

# Initialise DB on startup
init_db()


# ── Startup check ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            logger.info(f"Ollama reachable — models: {models}")
    except Exception as e:
        logger.warning(f"Ollama not reachable at startup: {e}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "ollama_host": OLLAMA_HOST, "model": OLLAMA_MODEL}


@app.get("/api/ollama/status")
async def ollama_status():
    """Check Ollama connectivity and list available models."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            data = r.json()
            models = [{"name": m["name"], "size_gb": round(m["size"] / 1e9, 1)} for m in data.get("models", [])]
            return {
                "reachable": True,
                "host": OLLAMA_HOST,
                "active_model": OLLAMA_MODEL,
                "available_models": models,
            }
    except Exception as e:
        return {"reachable": False, "host": OLLAMA_HOST, "error": str(e)}


@app.post("/api/jobs")
async def create_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext not in ("twbx", "twb", "pbix"):
        raise HTTPException(400, "Only .twbx, .twb, and .pbix files are supported")

    source_format = ext  # twbx, twb, or pbix
    target_format = "pbix" if ext in ("twbx", "twb") else "twbx"

    job_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{job_id}_{filename}"

    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    now = datetime.now().isoformat()
    with get_db() as db:
        db.execute(
            "INSERT INTO jobs (id, filename, source_format, target_format, status, created_at, updated_at, ollama_model) VALUES (?,?,?,?,?,?,?,?)",
            (job_id, filename, source_format, target_format, "queued", now, now, OLLAMA_MODEL),
        )
        for agent_name in AGENT_NAMES:
            db.execute(
                "INSERT INTO agent_steps (job_id, agent_name, status) VALUES (?,?,?)",
                (job_id, agent_name, "pending"),
            )
        db.commit()

    # Run pipeline in background thread (not FastAPI BackgroundTask — we use a thread
    # because the pipeline does blocking httpx calls to Ollama)
    t = threading.Thread(
        target=run_pipeline,
        args=(job_id, str(save_path), source_format, target_format, filename),
        daemon=True,
    )
    t.start()

    return {
        "job_id": job_id,
        "source_format": source_format,
        "target_format": target_format,
        "ollama_model": OLLAMA_MODEL,
    }


@app.get("/api/jobs")
def list_jobs():
    with get_db() as db:
        jobs = db.execute(
            "SELECT id, filename, source_format, target_format, status, created_at, hitl_status, ollama_model "
            "FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(j) for j in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        steps = db.execute(
            "SELECT id, job_id, agent_name, status, message, started_at, completed_at, output, ai_log "
            "FROM agent_steps WHERE job_id=? ORDER BY id",
            (job_id,),
        ).fetchall()

    return {
        **dict(job),
        "report": json.loads(job["report"]) if job["report"] else None,
        "steps": [dict(s) for s in steps],
    }


@app.post("/api/jobs/{job_id}/approve")
def approve_job(job_id: str):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        if job["status"] != "awaiting_review":
            raise HTTPException(400, f"Job status is '{job['status']}' — must be 'awaiting_review'")
        db.execute(
            "UPDATE jobs SET hitl_status='approved', status='completed', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), job_id),
        )
        db.commit()
    return {"status": "approved"}


@app.post("/api/jobs/{job_id}/reject")
def reject_job(job_id: str):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        db.execute(
            "UPDATE jobs SET hitl_status='rejected', status='rejected', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), job_id),
        )
        db.commit()
    return {"status": "rejected"}


class FormulaEdit(BaseModel):
    name: str
    translated_formula: str

class FormulasUpdate(BaseModel):
    formulas: List[FormulaEdit]

class FixFormulaRequest(BaseModel):
    original_formula: str
    translated_formula: str
    instructions: Optional[str] = None

@app.post("/api/jobs/{job_id}/review")
def run_post_migration_review(job_id: str, model_name: str = None):
    """
    Run deep post-migration review using advanced LLM.
    
    Args:
        job_id: Migration job ID
        model_name: Optional specific model (qwen2.5-coder:32b, llama3.3:70b, gemma2:27b)
                   If not provided, auto-selects best available model
    
    Returns:
        Detailed analysis with critical issues, warnings, and recommendations
    """
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        
        if job["status"] not in ("completed", "awaiting_review"):
            raise HTTPException(400, f"Job must be completed first. Current status: {job['status']}'")
        
        report = json.loads(job["report"]) if job["report"] else {}
        
        # Build context from report
        context = {
            "job_id": job_id,
            "report": report,
            "source_meta": report.get("source_meta", {}),
            "translated_formulas": report.get("translated_formulas", []),
            "field_inventory": report.get("field_inventory", []),
        }
        
        # Run post-migration review with specified or auto-selected model
        from agents.post_migration_review import PostMigrationReviewAgent
        
        logger.info(f"Starting post-migration review for job {job_id} with model: {model_name or 'auto-select'}")
        
        try:
            review_agent = PostMigrationReviewAgent(model_name=model_name)
            context = review_agent.run(context)
            
            # Update job report with review
            updated_report = context["report"]
            db.execute(
                "UPDATE jobs SET report=?, updated_at=? WHERE id=?",
                (json.dumps(updated_report), datetime.now().isoformat(), job_id),
            )
            db.commit()
            
            review_analysis = context.get("post_migration_review", {})
            model_used = context.get("review_model_used", "unknown")
            
            return {
                "status": "review_completed",
                "model_used": model_used,
                "analysis": review_analysis,
                "summary": {
                    "critical_issues": len(review_analysis.get("critical_issues", [])),
                    "warnings": len(review_analysis.get("warnings", [])),
                    "recommendations": len(review_analysis.get("recommendations", [])),
                    "overall_quality": review_analysis.get("review_summary", {}).get("overall_quality", "unknown"),
                    "migration_ready": review_analysis.get("review_summary", {}).get("migration_ready", False),
                }
            }
            
        except Exception as e:
            logger.error(f"Post-migration review failed: {e}", exc_info=True)
            raise HTTPException(500, f"Review failed: {str(e)}")


@app.get("/api/ollama/models")
async def list_ollama_models():
    """List all available Ollama models for review."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            data = r.json()
            models = [
                {
                    "name": m["name"],
                    "size_gb": round(m["size"] / 1e9, 1),
                    "modified": m.get("modified_at", ""),
                    "recommended_for_review": m["name"] in [
                        "qwen2.5-coder:32b", "qwen2.5:32b", 
                        "llama3.3:70b", "gemma2:27b"
                    ]
                }
                for m in data.get("models", [])
            ]
            return {
                "reachable": True,
                "host": OLLAMA_HOST,
                "models": models,
                "recommended_models": {
                    "qwen2.5-coder:32b": "Best for formula/code analysis",
                    "qwen2.5:32b": "Excellent reasoning capabilities",
                    "llama3.3:70b": "Strong analytical review",
                    "gemma2:27b": "Good technical validation",
                }
            }
    except Exception as e:
        return {"reachable": False, "host": OLLAMA_HOST, "error": str(e)}


@app.post("/api/jobs/{job_id}/formulas")
def update_formulas(job_id: str, payload: FormulasUpdate):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        
        report = json.loads(job["report"]) if job["report"] else {}
        translated = report.get("translated_formulas", [])
        
        # update translated formulas
        edit_map = {f.name: f.translated_formula for f in payload.formulas}
        for f in translated:
            if f["name"] in edit_map:
                f["translated_formula"] = edit_map[f["name"]]
                
        report["translated_formulas"] = translated
        
        # re-run deployment agent
        context = {
            "job_id": job_id,
            "source_path": job["source_path"],
            "report": report,
            "translated_formulas": translated,
        }
        
        from agents.reader import ReaderAgent
        from agents.deployment import DeploymentAgent
        
        try:
            ReaderAgent().run(context)
            DeploymentAgent().run(context)
        except Exception as e:
            logger.error(f"Failed to regenerate output: {e}", exc_info=True)
            raise HTTPException(500, f"Error regenerating output: {e}")
            
        output_path = context.get("output_path", job["output_path"])
        
        db.execute(
            "UPDATE jobs SET report=?, output_path=?, updated_at=? WHERE id=?",
            (json.dumps(report), output_path, datetime.now().isoformat(), job_id),
        )
        db.commit()
        
    return {"status": "success", "translated_formulas": translated}

@app.post("/api/jobs/{job_id}/fix_formula")
def fix_formula(job_id: str, payload: FixFormulaRequest):
    prompt = f"""You are an expert BI consultant. Fix this SQL/DAX formula.
Original: {payload.original_formula}
Current Translation: {payload.translated_formula}
User Instructions: {payload.instructions or 'Fix the syntax and ensure it is valid.'}

Return ONLY the corrected formula string. Do not include markdown formatting or explanations.
"""
    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=60.0
        )
        response.raise_for_status()
        data = response.json()
        corrected = data.get("response", "").strip()
        
        # Strip generic markdown block if present
        if corrected.startswith("```"):
            lines = corrected.split("\n")
            if len(lines) > 1:
                lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                corrected = "\n".join(lines).strip()
        
        return {"corrected_formula": corrected}
    except Exception as e:
        logger.error(f"Ollama fix_formula failed: {e}")
        raise HTTPException(500, f"Ollama error: {str(e)}")

@app.get("/api/jobs/{job_id}/download")
def download_output(job_id: str):
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        if job["status"] not in ("completed", "awaiting_review"):
            raise HTTPException(400, "Output not ready yet")
        output_path = job["output_path"]
        if not output_path or not Path(output_path).exists():
            raise HTTPException(404, "Output file not found")

    return FileResponse(
        path=output_path,
        filename=Path(output_path).name,
        media_type="application/zip",
    )
