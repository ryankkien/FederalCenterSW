import imaplib
import os
from uuid import uuid4

import azure.functions as func

from app.email_intake import EmailIntakeConfig, run_once
from app.observability import configure_observability, get_logger, log_context
from app.processing_worker import drain_queued_processing_jobs


configure_observability("backend-worker-function")
logger = get_logger(__name__)
app = func.FunctionApp()


@app.timer_trigger(
    schedule="%EMAIL_INTAKE_TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def email_intake_timer(timer: func.TimerRequest) -> None:
    with log_context(request_id=getattr(timer, "invocation_id", None) or str(uuid4())):
        if timer.past_due:
            logger.warning("Email intake timer is past due.")

        limit = int(os.getenv("EMAIL_INTAKE_LIMIT", "25"))
        config = EmailIntakeConfig.from_env()

        try:
            count = run_once(config, limit=limit)
        except imaplib.IMAP4.error:
            logger.exception(
                "IMAP login or mailbox operation failed. For Gmail, verify IMAP is enabled "
                "and the password is a Google app password.",
                extra={"email_intake_limit": limit},
            )
            raise

        logger.info("Email intake processed email batch", extra={"email_count": count})


@app.timer_trigger(
    schedule="%DOCUMENT_PROCESSING_TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def document_processing_timer(timer: func.TimerRequest) -> None:
    with log_context(request_id=getattr(timer, "invocation_id", None) or str(uuid4())):
        if timer.past_due:
            logger.warning("Document processing timer is past due.")

        limit = int(os.getenv("DOCUMENT_PROCESSING_LIMIT", "25"))
        summary = drain_queued_processing_jobs(limit=limit)

        logger.info(
            "Document processing worker processed job batch",
            extra={
                "processing_job_count": summary.processed,
                "processing_completed_count": summary.completed,
                "processing_failed_count": summary.failed,
                "processing_waiting_for_text_count": summary.waiting_for_text,
                "processing_queued_remaining_count": summary.queued_remaining,
            },
        )
