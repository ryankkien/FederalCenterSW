import imaplib
import logging
import os

import azure.functions as func

from app.email_intake import EmailIntakeConfig, run_once


app = func.FunctionApp()


@app.timer_trigger(
    schedule="%EMAIL_INTAKE_TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def email_intake_timer(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("Email intake timer is past due.")

    limit = int(os.getenv("EMAIL_INTAKE_LIMIT", "25"))
    config = EmailIntakeConfig.from_env()

    try:
        count = run_once(config, limit=limit)
    except imaplib.IMAP4.error:
        logging.exception(
            "IMAP login or mailbox operation failed. For Gmail, verify IMAP is enabled "
            "and the password is a Google app password."
        )
        raise

    logging.info("Email intake processed %s email(s).", count)
