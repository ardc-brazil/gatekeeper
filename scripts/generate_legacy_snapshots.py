"""
Generate JSON snapshots for legacy datasets with published DOIs.

This script generates static JSON snapshot files for all datasets that have
published DOIs but don't have snapshot files in MinIO yet. This is needed
to support the public dataset disclosure feature for legacy data.

Usage:
    python -m scripts.generate_legacy_snapshots --dry-run   # Preview changes
    python -m scripts.generate_legacy_snapshots             # Execute
    python -m scripts.generate_legacy_snapshots --force     # Regenerate all
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from uuid import UUID

from sqlalchemy import and_, or_

from app.config import settings
from app.database import Database
from app.gateway.object_storage.object_storage import ObjectStorageGateway
from app.model.dataset import VisibilityStatus
from app.model.db.dataset import Dataset as DatasetDBModel
from app.model.db.dataset import DatasetVersion as DatasetVersionDBModel
from app.model.db.doi import DOI as DOIDBModel
from app.model.doi import Mode as DOIMode
from app.model.doi import State as DOIState
from minio import Minio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate JSON snapshots for legacy datasets with published DOIs"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate snapshots even if they already exist",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        help="Process only a specific dataset ID (for debugging)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    return parser.parse_args()


def create_dataset_json_snapshot(
    dataset: DatasetDBModel,
    version: DatasetVersionDBModel,
    include_versions_list: bool = False,
) -> dict:
    """
    Create a JSON snapshot of the dataset metadata for public consumption.
    Replicates the logic from DatasetService._create_dataset_json_snapshot().
    """
    snapshot = dict(dataset.data) if dataset.data else {}

    snapshot.update(
        {
            "name": dataset.name,
            "dataset_id": str(dataset.id),
            "version_name": version.name,
            "doi_identifier": version.doi.identifier if version.doi else None,
            "doi_link": f"https://doi.org/{version.doi.identifier}"
            if version.doi
            else None,
            "doi_state": version.doi.state if version.doi else None,
            "publication_date": version.created_at.isoformat()
            if version.created_at
            else None,
        }
    )

    files = version.files_in or []

    extension_stats: dict[str, dict] = {}
    total_files = len(files)
    total_size = 0

    for file in files:
        if "." in file.name and len(file.name.split(".")) > 1:
            file_extension = "." + file.name.split(".")[-1]
        else:
            file_extension = "(no extension)"

        if file_extension not in extension_stats:
            extension_stats[file_extension] = {"count": 0, "total_size_bytes": 0}

        extension_stats[file_extension]["count"] += 1
        file_size = file.size_bytes or 0
        extension_stats[file_extension]["total_size_bytes"] += file_size
        total_size += file_size

    extensions_breakdown = [
        {
            "extension": ext,
            "count": stats["count"],
            "total_size_bytes": stats["total_size_bytes"],
        }
        for ext, stats in extension_stats.items()
    ]

    extensions_breakdown.sort(key=lambda x: (-x["count"], x["extension"]))

    snapshot["files_summary"] = {
        "total_files": total_files,
        "total_size_bytes": total_size,
        "extensions_breakdown": extensions_breakdown,
    }

    if include_versions_list:
        versions_info = []
        for v in dataset.versions:
            if v.is_enabled and v.doi is not None:
                doi_state = (
                    DOIState.FINDABLE.value
                    if hasattr(v.doi, "mode") and v.doi.mode == DOIMode.MANUAL.value
                    else v.doi.state
                )
                versions_info.append(
                    {
                        "id": str(v.id),
                        "name": v.name,
                        "doi_identifier": v.doi.identifier,
                        "doi_state": doi_state,
                        "created_at": v.created_at.isoformat()
                        if v.created_at
                        else None,
                    }
                )

        versions_info.sort(key=lambda x: x["created_at"] or "", reverse=True)
        snapshot["versions"] = versions_info

    return snapshot


def snapshot_exists(minio_gateway: ObjectStorageGateway, object_name: str) -> bool:
    """Check if a snapshot file already exists in MinIO."""
    try:
        minio_gateway.get_file(bucket_name="datamap", object_name=object_name)
        return True
    except FileNotFoundError:
        return False


def upload_snapshot(
    minio_gateway: ObjectStorageGateway, object_name: str, snapshot: dict
) -> None:
    """Upload a snapshot JSON file to MinIO."""
    json_bytes = json.dumps(snapshot, indent=2).encode("utf-8")
    minio_gateway.put_file(
        bucket_name="datamap",
        object_name=object_name,
        file_data=json_bytes,
        content_type="application/json",
    )


def get_latest_published_version(
    versions: list[DatasetVersionDBModel],
) -> DatasetVersionDBModel | None:
    """Get the latest published version by creation date."""
    published = [v for v in versions if v.is_enabled and v.doi is not None]
    if not published:
        return None
    return max(published, key=lambda v: v.created_at)


def main() -> int:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting legacy snapshot generation...")
    logger.info(f"  Dry run: {args.dry_run}")
    logger.info(f"  Force: {args.force}")
    if args.dataset_id:
        logger.info(f"  Dataset ID filter: {args.dataset_id}")

    db = Database(
        db_url=settings.DATABASE_URL,
        log_enabled=settings.DATABASE_LOG_ENABLED,
    )

    minio_client = Minio(
        endpoint=settings.MINIO_URL,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
        region=settings.MINIO_DEFAULT_REGION_ID,
    )
    minio_gateway = ObjectStorageGateway(minio_client=minio_client)

    stats = {
        "datasets_processed": 0,
        "versions_processed": 0,
        "snapshots_created": 0,
        "snapshots_skipped": 0,
        "latest_snapshots_created": 0,
        "visibility_updated": 0,
        "errors": 0,
    }

    try:
        with db.session() as session:
            query = (
                session.query(DatasetVersionDBModel)
                .join(DatasetDBModel, DatasetVersionDBModel.dataset_id == DatasetDBModel.id)
                .join(DOIDBModel, DOIDBModel.version_id == DatasetVersionDBModel.id)
                .filter(DatasetDBModel.is_enabled.is_(True))
                .filter(DatasetVersionDBModel.is_enabled.is_(True))
                .filter(
                    or_(
                        DOIDBModel.mode == DOIMode.MANUAL.value,
                        and_(
                            DOIDBModel.mode == DOIMode.AUTO.value,
                            DOIDBModel.state == DOIState.FINDABLE.value,
                        ),
                    )
                )
            )

            if args.dataset_id:
                query = query.filter(
                    DatasetDBModel.id == UUID(args.dataset_id)
                )

            versions = query.all()

            logger.info(f"Found {len(versions)} published versions to process")

            datasets_map: dict[UUID, list[DatasetVersionDBModel]] = defaultdict(list)
            for version in versions:
                datasets_map[version.dataset_id].append(version)

            logger.info(f"Grouped into {len(datasets_map)} datasets")

            for dataset_id, dataset_versions in datasets_map.items():
                try:
                    dataset = dataset_versions[0].dataset
                    logger.info(f"\nProcessing dataset: {dataset.name} ({dataset_id})")
                    stats["datasets_processed"] += 1

                    for version in dataset_versions:
                        stats["versions_processed"] += 1
                        version_object_name = (
                            f"snapshots/{dataset_id}-{version.name}.json"
                        )

                        exists = snapshot_exists(minio_gateway, version_object_name)

                        if exists and not args.force:
                            logger.debug(
                                f"  Skipping {version.name}: snapshot already exists"
                            )
                            stats["snapshots_skipped"] += 1
                            continue

                        action = "Would create" if args.dry_run else "Creating"
                        logger.info(f"  {action} snapshot for version {version.name}")

                        if not args.dry_run:
                            version_snapshot = create_dataset_json_snapshot(
                                dataset, version, include_versions_list=False
                            )
                            upload_snapshot(
                                minio_gateway, version_object_name, version_snapshot
                            )
                            stats["snapshots_created"] += 1
                        else:
                            stats["snapshots_created"] += 1

                    latest_version = get_latest_published_version(dataset_versions)
                    if latest_version:
                        latest_object_name = f"snapshots/{dataset_id}-latest.json"

                        action = "Would create" if args.dry_run else "Creating"
                        logger.info(
                            f"  {action} latest snapshot (version: {latest_version.name})"
                        )

                        if not args.dry_run:
                            latest_snapshot = create_dataset_json_snapshot(
                                dataset, latest_version, include_versions_list=True
                            )
                            upload_snapshot(
                                minio_gateway, latest_object_name, latest_snapshot
                            )
                            stats["latest_snapshots_created"] += 1
                        else:
                            stats["latest_snapshots_created"] += 1

                    if dataset.visibility != VisibilityStatus.PUBLIC:
                        action = "Would update" if args.dry_run else "Updating"
                        logger.info(f"  {action} visibility to PUBLIC")

                        if not args.dry_run:
                            dataset.visibility = VisibilityStatus.PUBLIC
                            session.add(dataset)
                            stats["visibility_updated"] += 1
                        else:
                            stats["visibility_updated"] += 1

                except Exception as e:
                    logger.error(f"  Error processing dataset {dataset_id}: {e}")
                    stats["errors"] += 1
                    continue

            if not args.dry_run:
                session.commit()
                logger.info("\nChanges committed to database")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1

    logger.info("\n" + "=" * 50)
    logger.info("Summary:")
    logger.info(f"  Datasets processed: {stats['datasets_processed']}")
    logger.info(f"  Versions processed: {stats['versions_processed']}")
    logger.info(f"  Snapshots created: {stats['snapshots_created']}")
    logger.info(f"  Snapshots skipped: {stats['snapshots_skipped']}")
    logger.info(f"  Latest snapshots created: {stats['latest_snapshots_created']}")
    logger.info(f"  Visibility updates: {stats['visibility_updated']}")
    logger.info(f"  Errors: {stats['errors']}")

    if args.dry_run:
        logger.info("\nThis was a DRY RUN - no changes were made")

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
