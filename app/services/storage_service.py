"""
app/services/storage_service.py
────────────────────────────────
File storage abstraction layer.

Two modes — chosen automatically based on whether S3 credentials are configured:

  S3Mode  — uploads to Cloudflare R2 (or AWS S3).
            Use this in production.
            Files are removed from the local disk after upload.

  LocalMode — saves to OUTPUT_DIR on disk.
              Use this in development when you haven't set up R2 yet.
              Files are served directly via FastAPI StaticFiles.

CLOUDFLARE R2 SETUP (5 minutes):
  1. Log in to dash.cloudflare.com → R2 Object Storage
  2. Create a bucket named "ats-ready-resumes"
  3. Settings → R2 API Tokens → Create Token (Object Read & Write)
  4. Copy Account ID, Access Key ID, Secret Access Key
  5. Fill in .env: S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
  6. (Optional) Add a custom domain to the bucket for CDN_BASE_URL

AWS S3 SETUP:
  - S3_ENDPOINT_URL: leave empty (boto3 uses default AWS endpoint)
  - S3_REGION: "us-east-1" (or your chosen region)
  - Same access key process via IAM
"""
import logging
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StorageService:
    """
    Upload, download-URL generation, and deletion of resume .docx files.
    Thread-safe: boto3 clients are thread-safe after creation.
    """

    def __init__(self):
        self._client = None   # lazy-initialised on first use

    # ── Private ───────────────────────────────────────────────────────────────

    def _get_client(self):
        """Build (and cache) the boto3 S3 client."""
        if self._client is None:
            kwargs = dict(
                region_name=settings.S3_REGION,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "adaptive"},
                ),
            )
            if settings.S3_ENDPOINT_URL:
                # Cloudflare R2 / MinIO / LocalStack
                kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _build_s3_key(self, user_id: int, filename: str) -> str:
        """
        Construct the S3 object key.
        Format:  resumes/{user_id}/{uuid}_{filename}

        The UUID prefix guarantees uniqueness even if a user generates
        multiple resumes for the same role at the same company.
        """
        uid = str(uuid.uuid4())[:8]
        safe_filename = filename.replace(" ", "_")
        return f"resumes/{user_id}/{uid}_{safe_filename}"

    # ── Public API ────────────────────────────────────────────────────────────

    def upload_resume(
        self,
        local_path: Path,
        user_id: int,
        filename: str,
    ) -> str:
        """
        Upload a .docx from `local_path` to S3/R2.
        Returns the S3 object key (not a URL — use get_download_url() for URLs).
        Deletes the local file after a successful upload.

        Raises StorageError on failure (caller should catch and surface to user).
        """
        if not settings.storage_use_s3:
            # Development fallback: just keep the file on disk
            logger.debug("S3 not configured — using local storage for %s", filename)
            return str(local_path)

        s3_key = self._build_s3_key(user_id, filename)
        try:
            client = self._get_client()
            client.upload_file(
                Filename=str(local_path),
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                ExtraArgs={
                    "ContentType": (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    # Browsers will prompt "Save As" with the original filename
                    "ContentDisposition": f'attachment; filename="{filename}"',
                },
            )
            logger.info("Uploaded %s → s3://%s/%s", filename, settings.S3_BUCKET_NAME, s3_key)

            # Clean up local temp file
            try:
                local_path.unlink()
            except OSError:
                logger.warning("Could not delete temp file %s", local_path)

            return s3_key

        except (BotoCoreError, ClientError) as exc:
            logger.error("S3 upload failed for %s: %s", filename, exc)
            raise StorageError(f"Failed to upload resume to storage: {exc}") from exc

    def get_download_url(self, s3_key: str, filename: str) -> str:
        """
        Return a URL the user can click to download the resume.

        Two strategies:
          - If CDN_BASE_URL is set, the bucket is public-access and we
            return a plain CDN URL (fast, no expiry).
          - Otherwise we generate a pre-signed URL valid for DOWNLOAD_URL_EXPIRY
            seconds (default 1 hour).  Secure: no public access needed.

        In local-storage mode (development), s3_key is an absolute path —
        we return a /outputs/... URL served by FastAPI StaticFiles.
        """
        if not settings.storage_use_s3:
            # Local mode — s3_key is a full Path string
            path = Path(s3_key)
            return f"/outputs/{path.name}"

        if settings.CDN_BASE_URL:
            return f"{settings.CDN_BASE_URL.rstrip('/')}/{s3_key}"

        # Pre-signed URL
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": s3_key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=settings.DOWNLOAD_URL_EXPIRY,
            )
            return url
        except (BotoCoreError, ClientError) as exc:
            logger.error("Failed to generate presigned URL for %s: %s", s3_key, exc)
            raise StorageError(f"Could not generate download link: {exc}") from exc

    def delete_resume(self, s3_key: str) -> None:
        """
        Delete a resume from S3.  Called when a user deletes a job application
        or requests GDPR erasure.  Silently ignores missing objects.
        """
        if not settings.storage_use_s3:
            try:
                Path(s3_key).unlink(missing_ok=True)
            except OSError:
                pass
            return

        try:
            client = self._get_client()
            client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
            logger.info("Deleted s3://%s/%s", settings.S3_BUCKET_NAME, s3_key)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("Could not delete S3 object %s: %s", s3_key, exc)

    def head_object(self, s3_key: str) -> bool:
        """Return True if the object exists in S3."""
        if not settings.storage_use_s3:
            return Path(s3_key).exists()
        try:
            self._get_client().head_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
            return True
        except ClientError:
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
storage_service = StorageService()
