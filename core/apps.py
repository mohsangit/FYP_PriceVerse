import json
import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        import threading

        from core.llm import warmup_ollama

        threading.Thread(target=warmup_ollama, daemon=True, name="ollama-warmup").start()
