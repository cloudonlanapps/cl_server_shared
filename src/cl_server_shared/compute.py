"""Shared compute module infrastructure."""

import argparse
import asyncio
import json
import logging
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

from .config import (
    WORKER_DATABASE_URL,
    COMPUTE_STORAGE_DIR,
    LOG_LEVEL,
    BROADCAST_TYPE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
)
from .database import Base, create_db_engine
from .models.job import Job
from .mqtt import get_broadcaster, shutdown_broadcaster

# Configure logging
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("compute-runner")


from .schemas import ComputeJobParams, ImageResizeParams, ImageConversionParams

class ComputeModule(ABC):
    """Base class for all compute modules."""

    @property
    @abstractmethod
    def supported_task_types(self) -> List[str]:
        """
        Return list of task types this module supports.

        Returns:
            List of task type strings (e.g., ["image_resize", "image_conversion"])
        """
        pass

    @abstractmethod
    async def process(
        self,
        job_id: str,
        task_type: str,
        params: ComputeJobParams,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Process a compute job.

        Args:
            job_id: Unique job identifier
            task_type: The type of task to perform (e.g. "image_resize")
            params: Validated job parameters (Pydantic model)
            progress_callback: Optional callback to report progress (0-100)

        Returns:
            Dictionary with:
            {
                "status": "ok" or "error",
                "output_files": [{file_id: str, metadata: dict}, ...],
                "task_output": {...},  # Task-specific results
                "error": Optional error message
            }
        """
        pass


def _execute_async_module(module, job_id, task_type, params, progress_callback):
    """Execute async compute module in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            module.process(job_id, task_type, params, progress_callback)
        )
        return result
    finally:
        loop.close()


def run_compute_job(module: ComputeModule):
    """
    Run a compute job using the provided module.
    
    This function handles:
    1. Parsing command line arguments (job_id)
    2. Setting up database and MQTT connection
    3. Retrieving job details
    4. Parsing parameters
    5. Executing the module
    6. Handling results and updating job status
    """
    parser = argparse.ArgumentParser(description="Run a compute job")
    parser.add_argument("--job-id", required=True, help="Job ID to process")
    args = parser.parse_args()

    job_id = args.job_id
    logger.info(f"Runner started for job {job_id}")

    # Setup database
    engine = create_db_engine(WORKER_DATABASE_URL)
    
    # Create tables if they don't exist (safety check)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Setup broadcaster
    broadcaster = get_broadcaster(
        broadcast_type=BROADCAST_TYPE,
        broker=MQTT_BROKER,
        port=MQTT_PORT,
        topic=MQTT_TOPIC
    )

    try:
        # 1. Get Job
        job = db.query(Job).filter_by(job_id=job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            sys.exit(1)

        # 2. Update Status -> Processing
        job.status = "processing"
        job.started_at = int(time.time() * 1000)
        db.commit()

        broadcaster.publish_event("started", job_id, {"status": "processing"})

        # 3. Parse Parameters
        task_type = job.task_type
        logger.info(f"Loading module for {task_type}")
        
        # Verify module supports this task
        if task_type not in module.supported_task_types:
            logger.warning(f"Module supports {module.supported_task_types}, but job is {task_type}")

        try:
            params_dict = json.loads(job.params)
            
            if task_type == "image_resize":
                params = ImageResizeParams(**params_dict)
            elif task_type == "image_conversion":
                params = ImageConversionParams(**params_dict)
            else:
                # Fallback to base params if unknown task type
                params = ComputeJobParams(**params_dict)
                
        except Exception as e:
            logger.error(f"Failed to parse parameters: {e}")
            raise ValueError(f"Invalid parameters: {e}")

        # 4. Define Progress Callback
        def progress_callback(percentage: int):
            try:
                job.progress = min(99, percentage)
                db.commit()
                broadcaster.publish_event("progress", job_id, {"progress": percentage})
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")

        # 5. Execute (Async wrapper)
        logger.info("Executing module...")
        result = _execute_async_module(
            module, job_id, task_type, params, progress_callback
        )

        # 7. Handle Result
        status = result.get("status", "error")
        error = result.get("error")
        task_output = result.get("task_output", {})

        if status == "ok":
            logger.info("Job completed successfully")
            job.status = "completed"
            job.progress = 100
            job.task_output = json.dumps(task_output)
            job.completed_at = int(time.time() * 1000)
            db.commit()
            broadcaster.publish_event(
                "completed", job_id, {"task_output": task_output}
            )
        else:
            logger.error(f"Job failed: {error}")
            job.status = "error"
            job.error_message = error
            job.completed_at = int(time.time() * 1000)
            db.commit()
            broadcaster.publish_event("failed", job_id, {"error": error})
            sys.exit(1)

    except Exception as e:
        logger.exception(f"Runner exception: {e}")
        try:
            job = db.query(Job).filter_by(job_id=job_id).first()
            if job:
                job.status = "error"
                job.error_message = str(e)
                job.completed_at = int(time.time() * 1000)
                db.commit()
                broadcaster.publish_event("failed", job_id, {"error": str(e)})
        except:
            pass
        sys.exit(1)
    finally:
        db.close()
        shutdown_broadcaster()
