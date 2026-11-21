from celery import shared_task


@shared_task(name="scans.ping")
def ping() -> str:
    return "pong"
