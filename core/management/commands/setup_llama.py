import os
import shutil
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Guide Meta Llama model download and verify Llama Stack connectivity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--download",
            action="store_true",
            help="Run the official llama model download command (requires llama-models).",
        )

    def handle(self, *args, **options):
        model_id = getattr(settings, "LLAMA_MODEL_ID", "Llama3.1-8B-Instruct")
        download_url = getattr(settings, "LLAMA_DOWNLOAD_URL", "")
        base_url = getattr(settings, "LLAMA_STACK_BASE_URL", "http://localhost:8321")

        self.stdout.write(self.style.MIGRATE_HEADING("Meta Llama setup"))
        self.stdout.write("")
        self.stdout.write("1. List available models:")
        self.stdout.write("   llama model list")
        self.stdout.write("   llama model list --show-all")
        self.stdout.write("")
        self.stdout.write("2. Download the selected model:")
        self.stdout.write(f"   llama model download --source meta --model-id {model_id}")
        if download_url:
            self.stdout.write("   Paste your unique custom URL from Meta when prompted.")
        else:
            self.stdout.write(
                "   Set LLAMA_DOWNLOAD_URL in .env with your Meta signed download URL."
            )
        self.stdout.write("")
        self.stdout.write("3. Start the Llama Stack inference server:")
        self.stdout.write("   llama stack run")
        self.stdout.write("")
        self.stdout.write(f"4. Chatbot stack URL: {base_url}")
        self.stdout.write(f"   Chatbot model ID: {model_id}")
        self.stdout.write("")

        llama_bin = shutil.which("llama") or shutil.which("llama-model")
        if llama_bin:
            self.stdout.write(self.style.SUCCESS(f"Found CLI: {llama_bin}"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Llama CLI not found. Install with: pip install llama-models llama-stack"
                )
            )

        if options["download"]:
            if not llama_bin:
                self.stderr.write(self.style.ERROR("Cannot download — Llama CLI is missing."))
                return

            env = os.environ.copy()
            if download_url:
                env["LLAMA_DOWNLOAD_URL"] = download_url

            cmd = [llama_bin, "model", "download", "--source", "meta", "--model-id", model_id]
            self.stdout.write(f"Running: {' '.join(cmd)}")
            try:
                subprocess.run(cmd, check=False, env=env)
            except OSError as exc:
                self.stderr.write(self.style.ERROR(f"Download failed: {exc}"))

        try:
            from core.llm.llama_client import generate_chat_reply

            probe = generate_chat_reply(
                "You are a connectivity probe.",
                "Reply with OK only.",
                "[]",
            )
            if probe.ok:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Inference is reachable via {probe.source}."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Inference not reachable ({probe.source}: {probe.error or 'unknown'}). "
                        "For Ollama: ensure it is running and LLAMA_STACK_BASE_URL=http://localhost:11434"
                    )
                )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Probe failed: {exc}"))
