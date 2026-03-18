"""MeiliSearch integration for message indexing and searching."""

import os
import platform
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import meilisearch
from meilisearch.errors import MeilisearchApiError
from phdkit.log import Logger, LogOutput

from .config import MeiliSearchConfig, get_data_dir

logger = Logger(__name__, outputs=[LogOutput.stdout()])


@dataclass
class MessageDocument:
    """Represents a message document for indexing."""

    id: str
    chat_id: int  # Always numeric ID
    message_id: int
    session_name: str
    text: str
    sender_id: int | None
    sender_name: str | None
    date: int  # Unix timestamp
    chat_title: str | None


class MeiliSearchManager:
    """Manages MeiliSearch instance and message indexing."""

    def __init__(self, config: MeiliSearchConfig):
        self.config = config
        self.process: subprocess.Popen | None = None
        self.client: meilisearch.Client | None = None
        self.index_name = "messages"

    def _ensure_meilisearch_binary(self) -> str:
        """Ensure MeiliSearch binary is available, install if needed.

        Returns:
            Path to the meilisearch binary
        """
        # Check if meilisearch is in PATH
        meilisearch_path = shutil.which("meilisearch")
        if meilisearch_path:
            logger.info("MeiliSearch", f"Found meilisearch in PATH: {meilisearch_path}")
            return "meilisearch"

        # Check if ./meilisearch exists in current directory
        local_meilisearch = Path.cwd() / "meilisearch"
        if local_meilisearch.exists() and local_meilisearch.is_file():
            logger.info("MeiliSearch", f"Found local meilisearch: {local_meilisearch}")
            return str(local_meilisearch)

        # Not found, need to install
        logger.info("MeiliSearch", "MeiliSearch binary not found, installing...")

        try:
            # Detect platform and architecture
            system = platform.system().lower()
            machine = platform.machine().lower()

            # Determine the correct binary suffix
            if system == "linux":
                if machine in ("x86_64", "amd64"):
                    binary_suffix = "linux-amd64"
                elif machine in ("aarch64", "arm64"):
                    binary_suffix = "linux-aarch64"
                else:
                    raise RuntimeError(f"Unsupported Linux architecture: {machine}")
            elif system == "darwin":
                if machine in ("x86_64", "amd64"):
                    binary_suffix = "macos-amd64"
                elif machine in ("arm64", "aarch64"):
                    binary_suffix = "macos-apple-silicon"
                else:
                    raise RuntimeError(f"Unsupported macOS architecture: {machine}")
            elif system == "windows":
                if machine in ("x86_64", "amd64"):
                    binary_suffix = "windows-amd64.exe"
                else:
                    raise RuntimeError(f"Unsupported Windows architecture: {machine}")
            else:
                raise RuntimeError(f"Unsupported operating system: {system}")

            # Download MeiliSearch from GitHub releases
            version = "v1.39.0"
            download_url = f"https://github.com/meilisearch/meilisearch/releases/download/{version}/meilisearch-{binary_suffix}"

            logger.info("MeiliSearch", f"Downloading from {download_url}")

            # Download to local directory
            download_path = local_meilisearch
            urllib.request.urlretrieve(download_url, download_path)

            # Make executable (Unix-like systems)
            if system in ("linux", "darwin"):
                os.chmod(download_path, 0o755)

            logger.info("MeiliSearch", "MeiliSearch installed successfully")

            if download_path.exists():
                return str(download_path)
            else:
                raise RuntimeError("MeiliSearch binary not found after download")

        except Exception as e:
            raise RuntimeError(f"Failed to install MeiliSearch: {e}")

    def start(self) -> None:
        """Start MeiliSearch if not already running."""
        # Check if already running
        try:
            client = meilisearch.Client(self.config.host, self.config.master_key)
            client.health()
            logger.info("MeiliSearch", "MeiliSearch is already running")
            self.client = client
            self._setup_index()
            return
        except Exception:
            pass

        # Ensure MeiliSearch binary is available
        meilisearch_binary = self._ensure_meilisearch_binary()

        # Start MeiliSearch process
        logger.info("MeiliSearch", "Starting MeiliSearch...")

        # MeiliSearch data directory
        data_dir = get_data_dir() / "meilisearch_data"
        data_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            meilisearch_binary,
            "--db-path",
            str(data_dir),
            "--http-addr",
            self.config.host.replace("http://", ""),
            "--max-indexing-memory",
            self.config.memory_limit,
        ]

        if self.config.master_key:
            cmd.extend(["--master-key", self.config.master_key])

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for MeiliSearch to be ready
        max_retries = 30
        for i in range(max_retries):
            # Check if process died
            if self.process and self.process.poll() is not None:
                stderr_output = (
                    self.process.stderr.read() if self.process.stderr else ""
                )
                stdout_output = (
                    self.process.stdout.read() if self.process.stdout else ""
                )
                raise RuntimeError(
                    f"MeiliSearch process died with code {self.process.returncode}\n"
                    f"Stdout: {stdout_output}\n"
                    f"Stderr: {stderr_output}"
                )

            try:
                client = meilisearch.Client(self.config.host, self.config.master_key)
                client.health()
                logger.info("MeiliSearch", "MeiliSearch started successfully")
                self.client = client
                break
            except Exception as e:
                if i == max_retries - 1:
                    # Capture process output for debugging
                    stderr_output = ""
                    stdout_output = ""
                    if self.process:
                        if self.process.stderr:
                            stderr_output = self.process.stderr.read()
                        if self.process.stdout:
                            stdout_output = self.process.stdout.read()
                    raise RuntimeError(
                        f"Failed to start MeiliSearch: {e}\n"
                        f"Stdout: {stdout_output}\n"
                        f"Stderr: {stderr_output}"
                    )
                time.sleep(1)

        # Setup index after connection is established
        self._setup_index()

    def _setup_index(self) -> None:
        """Setup the messages index with proper configuration."""
        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")

        try:
            index = self.client.get_index(self.index_name)
            logger.info("Index Setup", f"Using existing index: {self.index_name}")
        except MeilisearchApiError:
            # Create new index
            logger.info("Index Setup", f"Creating new index: {self.index_name}")
            task = self.client.create_index(self.index_name, {"primaryKey": "id"})
            # Wait for index creation to complete
            self.client.wait_for_task(task.task_uid)
            index = self.client.get_index(self.index_name)

        # Configure searchable attributes
        task = index.update_searchable_attributes(["text", "sender_name", "chat_title"])
        self.client.wait_for_task(task.task_uid)

        # Configure filterable attributes
        task = index.update_filterable_attributes(
            ["chat_id", "session_name", "sender_id", "date"]
        )
        self.client.wait_for_task(task.task_uid)

        # Configure sortable attributes
        task = index.update_sortable_attributes(["date"])
        self.client.wait_for_task(task.task_uid)

        logger.info("Index Setup", "Index configured successfully")

    def stop(self) -> None:
        """Stop MeiliSearch process if it was started by us."""
        if self.process:
            logger.info("MeiliSearch", "Stopping MeiliSearch...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            logger.info("MeiliSearch", "MeiliSearch stopped")

    def get_index(self):
        """Get the MeiliSearch index object."""
        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")
        return self.client.get_index(self.index_name)

    def get_document_count(self) -> int:
        """Get the total number of documents in the index."""
        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")

        try:
            index = self.client.get_index(self.index_name)
            stats = index.get_stats()
            return getattr(stats, "numberOfDocuments", 0) if stats else 0
        except Exception:
            return 0

    def get_indexed_document_ids(self) -> set[str]:
        """Get all document IDs that are already indexed."""
        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")

        try:
            index = self.client.get_index(self.index_name)
            stats = index.get_stats()
            total_docs = getattr(stats, "numberOfDocuments", 0) if stats else 0
            logger.info("MeiliSearch Stats", f"Index has {total_docs} total documents")

            # Fetch all document IDs in batches
            doc_ids = set()
            offset = 0
            limit = 1000

            batch_count = 0
            while True:
                results = index.get_documents(
                    {"limit": limit, "offset": offset, "fields": ["id"]}
                )
                if not results.results:
                    break
                batch_count += 1
                # results.results is a list of dicts
                for doc in results.results:
                    if isinstance(doc, dict) and "id" in doc:
                        doc_ids.add(doc["id"])
                offset += limit
                if len(results.results) < limit:
                    break

            logger.info(
                "MeiliSearch IDs",
                f"Fetched {len(doc_ids)} document IDs in {batch_count} batches",
            )
            # Log a few sample IDs
            if doc_ids:
                sample_ids = list(doc_ids)[:3]
                logger.info("MeiliSearch Debug", f"Sample IDs: {sample_ids}")
            return doc_ids
        except Exception as e:
            logger.error("MeiliSearch Error", f"Failed to fetch indexed IDs: {e}")
            # If index doesn't exist or error, return empty set
            return set()

    def index_messages(self, messages: list[MessageDocument], index=None) -> None:
        """Index a batch of messages."""
        logger.info(
            "MeiliSearch Debug", f"index_messages called with {len(messages)} messages"
        )

        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")

        if not messages:
            return

        if index is None:
            logger.info("MeiliSearch Debug", "About to call get_index")
            index = self.client.get_index(self.index_name)
            logger.info("MeiliSearch Debug", "get_index completed")
        else:
            logger.info("MeiliSearch Debug", "Using provided index object")

        logger.info("MeiliSearch Debug", "Building document list")
        documents = [
            {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "message_id": msg.message_id,
                "session_name": msg.session_name,
                "text": msg.text,
                "sender_id": msg.sender_id,
                "sender_name": msg.sender_name,
                "date": msg.date,
                "chat_title": msg.chat_title,
            }
            for msg in messages
        ]
        logger.info(
            "MeiliSearch Debug", f"Document list built with {len(documents)} items"
        )

        logger.info("MeiliSearch Debug", "About to call add_documents")
        task = index.add_documents(documents)
        logger.info("MeiliSearch Debug", "add_documents call completed")

        logger.info(
            "MeiliSearch",
            f"Submitted batch of {len(documents)} documents to index (task: {task.task_uid})",
        )
        # Log first doc ID for debugging
        if documents:
            logger.info("MeiliSearch Debug", f"Sample doc ID: {documents[0]['id']}")

    def search(
        self, query: str, limit: int = 20, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search for messages."""
        if not self.client:
            raise RuntimeError("MeiliSearch client not initialized")

        index = self.client.get_index(self.index_name)

        search_params: dict[str, Any] = {
            "limit": limit,
            "sort": ["date:desc"],
        }

        if filters:
            filter_parts = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_parts.append(f"{key} IN [{', '.join(map(str, value))}]")
                else:
                    filter_parts.append(f"{key} = {value}")
            if filter_parts:
                search_params["filter"] = " AND ".join(filter_parts)

        results = index.search(query, search_params)
        return results["hits"]  # type: ignore
