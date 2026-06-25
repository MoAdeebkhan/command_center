"""
Pipeline orchestrator — runs all 7 agents in sequence in a background thread,
updating the DB with progress at each step.
"""
import json
import logging
import threading
from datetime import datetime

from database import get_db
from agents.reader import ReaderAgent
from agents.business_logic import BusinessLogicAgent
from agents.extraction import ExtractionAgent
from agents.conversion import ConversionAgent
from agents.documentation import DocumentationAgent
from agents.validation import ValidationAgent
from agents.deployment import DeploymentAgent
from agents.post_migration_review import PostMigrationReviewAgent

logger = logging.getLogger(__name__)

AGENT_CLASSES = [
    ReaderAgent,
    BusinessLogicAgent,
    ExtractionAgent,
    ConversionAgent,
    DocumentationAgent,
    ValidationAgent,
    DeploymentAgent,
]

# Optional post-migration review agent (can be run separately)
POST_REVIEW_AGENT = PostMigrationReviewAgent


def _update_job(db, job_id: str, status: str):
    db.execute(
        "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), job_id),
    )
    db.commit()


def _start_step(db, step_id: int):
    db.execute(
        "UPDATE agent_steps SET status='running', started_at=? WHERE id=?",
        (datetime.now().isoformat(), step_id),
    )
    db.commit()


def _complete_step(db, step_id: int, message: str, output: dict = None, ai_log: str = None):
    db.execute(
        "UPDATE agent_steps SET status='completed', message=?, completed_at=?, output=?, ai_log=? WHERE id=?",
        (
            message,
            datetime.now().isoformat(),
            json.dumps(output) if output else None,
            ai_log,
            step_id,
        ),
    )
    db.commit()


def _fail_step(db, step_id: int, error: str):
    db.execute(
        "UPDATE agent_steps SET status='failed', message=?, completed_at=? WHERE id=?",
        (f"Error: {error}", datetime.now().isoformat(), step_id),
    )
    db.commit()


def run_pipeline(job_id: str, filepath: str, source_format: str, target_format: str, filename: str):
    """Execute the full 7-agent pipeline in a background thread."""
    db = get_db()

    try:
        _update_job(db, job_id, "running")

        # Shared context passed between agents
        context = {
            "job_id": job_id,
            "filepath": filepath,
            "source_format": source_format,
            "target_format": target_format,
            "filename": filename,
        }

        for AgentClass in AGENT_CLASSES:
            agent = AgentClass()

            # Get step record
            row = db.execute(
                "SELECT id FROM agent_steps WHERE job_id=? AND agent_name=?",
                (job_id, agent.name),
            ).fetchone()
            if not row:
                logger.warning(f"No step row found for agent {agent.name}")
                continue

            step_id = row["id"]
            _start_step(db, step_id)

            try:
                context = agent.run(context)

                # Extract message and output from context
                msg_key = f"{agent.name.lower().replace(' ', '_')}_message"
                log_key = f"{agent.name.lower().replace(' ', '_')}_ai_log"

                # Fallback message keys
                msg_map = {
                    "Reader Agent": "reader_message",
                    "Business Logic Agent": "business_logic_message",
                    "Extraction Agent": "extraction_message",
                    "Conversion Agent": "conversion_message",
                    "Documentation Agent": "documentation_message",
                    "Validation Agent": "validation_message",
                    "Deployment Agent": "deployment_message",
                }
                ai_log_map = {
                    "Business Logic Agent": "business_logic_ai_log",
                    "Extraction Agent": "extraction_ai_log",
                    "Documentation Agent": "documentation_ai_log",
                    "Validation Agent": "validation_ai_log",
                }

                message = context.get(msg_map.get(agent.name, ""), f"{agent.name} completed")
                ai_log = context.get(ai_log_map.get(agent.name, ""), None)

                _complete_step(db, step_id, message, output=None, ai_log=ai_log)

            except Exception as e:
                logger.error(f"Agent {agent.name} failed: {e}", exc_info=True)
                _fail_step(db, step_id, str(e))
                # Don't abort — continue with remaining agents where possible

        # Save final report and output path
        final_report = context.get("report", {})
        output_path = context.get("output_path", "")

        db.execute(
            "UPDATE jobs SET status='awaiting_review', report=?, output_path=?, updated_at=? WHERE id=?",
            (
                json.dumps(final_report),
                output_path,
                datetime.now().isoformat(),
                job_id,
            ),
        )
        db.commit()

    except Exception as e:
        logger.error(f"Pipeline fatal error for job {job_id}: {e}", exc_info=True)
        _update_job(db, job_id, "failed")
        db.execute(
            "UPDATE agent_steps SET status='failed', message=? WHERE job_id=? AND status='running'",
            (str(e), job_id),
        )
        db.commit()
    finally:
        db.close()
