# RFC 002: Abandoned Dataset Cleanup

| Status | Proposed |
|--------|----------|
| Author | DataMap Team |
| Created | 2026-01-19 |
| Updated | 2026-01-19 |

## Summary

This RFC proposes a two-part solution to address the accumulation of empty/abandoned datasets in the database. The problem arises because the current "new dataset" flow immediately creates a database record when users click the button, even if they're just exploring. Many users abandon the flow, leaving orphaned DRAFT datasets with no files.

The solution combines:
1. **Frontend: Two-Step Wizard** - Require users to enter a title before creating the dataset
2. **Backend: Cleanup Job** - Automatically delete abandoned empty DRAFT datasets after 3 days

## Motivation

### Problem Statement

1. **Poor UX Causing Data Pollution**: When users click "New Dataset", a blank dataset is immediately created in the backend (with empty title). This is required because TUS file uploads need a dataset ID for authorization. However, many users:
   - Click the button just to explore
   - Navigate away before uploading files
   - Start but never complete the process

2. **Database Clutter**: The result is a growing number of empty datasets appearing in the list, confusing legitimate users and cluttering the UI.

3. **No Cleanup Mechanism**: Currently, there's no way to distinguish intentionally empty datasets from abandoned ones, and no automatic cleanup.

### Current Flow

```
User clicks "New Dataset"
    ↓
useEffect in new.tsx triggers immediately
    ↓
POST /datasets { title: "" } → Creates DRAFT dataset with empty name
    ↓
User may abandon at this point ← PROBLEM: Empty dataset persists
    ↓
(if continues) User uploads files and fills form
    ↓
PUT /datasets/{id} → Updates title and metadata
    ↓
POST /datasets/{id}/versions/{v}/publish → Publishes
```

### Goals

- Prevent creation of truly empty datasets (no title, no intent)
- Automatically clean up abandoned datasets that slip through
- Maintain the ability to upload files before finalizing metadata
- Minimize disruption to legitimate users

## Technical Design

### Part 1: Two-Step Wizard (Frontend)

#### Changes to `datamap-webapp/pages/app/datasets/new.tsx`

**Remove automatic dataset creation:**

The current `useEffect` that immediately creates a dataset on page load will be removed:

```typescript
// REMOVE THIS:
useEffect(() => {
  if (!datasetPrototyping?.createDatasetResponseV2?.id) {
    bffGateway.createNewDataset({ title: "" }).then(...)
  }
}, [datasetPrototyping])
```

**Add title modal state:**

```typescript
const [showTitleModal, setShowTitleModal] = useState(true);
const [pendingTitle, setPendingTitle] = useState('');
const [titleError, setTitleError] = useState('');
```

**Add title submission handler:**

```typescript
async function handleTitleSubmit() {
  const trimmedTitle = pendingTitle.trim();

  if (trimmedTitle.length < 3) {
    setTitleError('Title must be at least 3 characters');
    return;
  }

  try {
    const createDatasetResponseV2 = await bffGateway.createNewDataset({
      title: trimmedTitle,
    });

    const request = { file: { id: createDatasetResponseV2.id } };
    const fileUploadAuthTokenResponse = await bffGateway.createUploadFileAuthToken(request);

    setDatasetPrototyping({ createDatasetResponseV2, fileUploadAuthTokenResponse });
    setShowTitleModal(false);
  } catch (error) {
    setTitleError('Failed to create dataset. Please try again.');
  }
}
```

**Add title modal component:**

```tsx
<Modal
  title="Create New Dataset"
  show={showTitleModal && !datasetPrototyping?.createDatasetResponseV2?.id}
  confimButtonText="Continue"
  cancelButtonText="Cancel"
  confim={handleTitleSubmit}
  cancel={() => Router.push('/app/datasets')}
>
  <div className="space-y-4">
    <p className="text-sm text-gray-600">
      Enter a title for your dataset to get started. You can upload files and add more details on the next screen.
    </p>
    <div>
      <label htmlFor="initialTitle" className="block mb-2 text-sm font-medium">
        Dataset Title *
      </label>
      <input
        type="text"
        id="initialTitle"
        value={pendingTitle}
        onChange={(e) => {
          setPendingTitle(e.target.value);
          setTitleError('');
        }}
        onKeyDown={(e) => e.key === 'Enter' && handleTitleSubmit()}
        placeholder="Enter dataset title"
        className="w-full p-2 border rounded"
        autoFocus
      />
      {titleError && (
        <p className="text-xs text-error-600 mt-1">{titleError}</p>
      )}
    </div>
  </div>
</Modal>
```

**Update initial form values:**

```typescript
const initialValues: FormValues = {
  datasetTitle: datasetPrototyping?.createDatasetResponseV2?.name || '',
  urls: [{ url: '', confirmed: false }],
  uploadedDataFiles: [],
  remoteFilesCount: 0
};
```

#### New User Flow

```
User clicks "New Dataset"
    ↓
Modal appears: "Enter a title for your dataset"
    ↓
User clicks Cancel → Redirects to /app/datasets (no dataset created)
    ↓
User enters title (min 3 chars) and clicks Continue
    ↓
POST /datasets { title: "User's Title" } → Creates DRAFT with real title
    ↓
Modal closes, upload form appears with title pre-filled
    ↓
User uploads files and completes form
    ↓
Publish dataset
```

### Part 2: Cleanup Job (Backend)

#### New Repository Methods

Add to `gatekeeper/app/repository/dataset.py`:

```python
from datetime import datetime, timedelta
from sqlalchemy import select, not_, exists
from app.model.db.dataset import Dataset, DatasetVersion, DesignState
from app.model.db.data_file import version_data_file_association

def fetch_abandoned_empty_datasets(
    self,
    days_inactive: int = 3
) -> List[Dataset]:
    """
    Fetch datasets that are:
    - In DRAFT state
    - Have is_enabled = True (not already deleted)
    - Have no files in any version
    - Have not been updated in `days_inactive` days
    - Have no DOI assigned to any version
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)

    with self._session_factory() as session:
        # Subquery: datasets that have at least one file
        datasets_with_files = (
            session.query(DatasetVersion.dataset_id)
            .join(version_data_file_association)
            .distinct()
            .subquery()
        )

        # Subquery: datasets that have a DOI
        datasets_with_dois = (
            session.query(DatasetVersion.dataset_id)
            .filter(DatasetVersion.doi_identifier.isnot(None))
            .distinct()
            .subquery()
        )

        query = (
            session.query(Dataset)
            .filter(Dataset.design_state == DesignState.DRAFT)
            .filter(Dataset.is_enabled == True)
            .filter(Dataset.updated_at < cutoff_date)
            .filter(~Dataset.id.in_(select(datasets_with_files.c.dataset_id)))
            .filter(~Dataset.id.in_(select(datasets_with_dois.c.dataset_id)))
            .order_by(Dataset.created_at.asc())
        )

        return query.all()

def hard_delete_dataset(self, dataset_id: UUID) -> bool:
    """
    Permanently delete a dataset and all related records.
    Should only be used for empty DRAFT datasets with no files.

    Returns True if deleted, False if not found.
    """
    with self._session_factory() as session:
        dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return False

        # Delete versions first (they have FK to dataset)
        for version in dataset.versions:
            session.delete(version)

        session.delete(dataset)
        session.commit()
        return True
```

#### New Service

Create `gatekeeper/app/service/cleanup.py`:

```python
"""Service for cleaning up abandoned/empty datasets."""
import logging
from typing import List
from uuid import UUID

from app.repository.dataset import DatasetRepository


class CleanupService:
    """
    Handles cleanup of abandoned datasets.

    An abandoned dataset is defined as:
    - DRAFT state (never published)
    - No files uploaded
    - No DOI assigned
    - No activity for X days (configurable)
    """

    def __init__(
        self,
        dataset_repository: DatasetRepository,
        days_inactive: int = 3,
    ):
        self._logger = logging.getLogger("service:CleanupService")
        self._repository = dataset_repository
        self._days_inactive = days_inactive

    def cleanup_abandoned_empty_datasets(self) -> dict:
        """
        Find and permanently delete abandoned empty datasets.

        Returns:
            dict with cleanup statistics:
            - found: number of abandoned datasets found
            - deleted: number successfully deleted
            - failed: number that failed to delete
            - deleted_ids: list of deleted dataset UUIDs
        """
        self._logger.info(
            f"Starting cleanup of abandoned empty datasets "
            f"(inactive for {self._days_inactive}+ days)"
        )

        abandoned_datasets = self._repository.fetch_abandoned_empty_datasets(
            days_inactive=self._days_inactive
        )

        self._logger.info(f"Found {len(abandoned_datasets)} abandoned datasets")

        deleted_count = 0
        failed_count = 0
        deleted_ids = []

        for dataset in abandoned_datasets:
            try:
                self._logger.info(
                    f"Deleting abandoned dataset: id={dataset.id}, "
                    f"name='{dataset.name}', created_at={dataset.created_at}, "
                    f"updated_at={dataset.updated_at}"
                )

                success = self._repository.hard_delete_dataset(dataset.id)
                if success:
                    deleted_count += 1
                    deleted_ids.append(str(dataset.id))
                else:
                    self._logger.warning(f"Dataset {dataset.id} not found during delete")
                    failed_count += 1

            except Exception as e:
                self._logger.error(
                    f"Failed to delete dataset {dataset.id}: {e}",
                    exc_info=True
                )
                failed_count += 1

        result = {
            "found": len(abandoned_datasets),
            "deleted": deleted_count,
            "failed": failed_count,
            "deleted_ids": deleted_ids,
        }

        self._logger.info(f"Cleanup completed: {result}")
        return result
```

#### Internal API Endpoint

Create `gatekeeper/app/controller/v1/internal/cleanup.py`:

```python
"""Internal endpoints for scheduled maintenance tasks."""
from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.service.cleanup import CleanupService

router = APIRouter(prefix="/cleanup", tags=["internal-cleanup"])


@router.post("/abandoned-datasets")
@inject
async def cleanup_abandoned_datasets(
    service: CleanupService = Depends(Provide[Container.cleanup_service]),
) -> dict:
    """
    Trigger cleanup of abandoned empty datasets.

    This endpoint should be called by an external scheduler (cron, k8s cronjob)
    on a regular basis (recommended: daily at low-traffic hours).

    Returns:
        Statistics about the cleanup operation:
        - found: number of abandoned datasets identified
        - deleted: number successfully deleted
        - failed: number that failed to delete
        - deleted_ids: UUIDs of deleted datasets
    """
    return service.cleanup_abandoned_empty_datasets()
```

#### Container Registration

Add to `gatekeeper/app/container.py`:

```python
from app.service.cleanup import CleanupService

# In the Container class:
cleanup_service = providers.Factory(
    CleanupService,
    dataset_repository=dataset_repository,
    days_inactive=3,  # Could be made configurable via config
)
```

#### Router Registration

Update `gatekeeper/app/controller/v1/internal/__init__.py` to include the cleanup router.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (datamap-webapp)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User clicks "New Dataset"                                           │
│         ↓                                                            │
│  ┌─────────────────┐    Cancel    ┌─────────────────┐               │
│  │  Title Modal    │ ──────────→  │ /app/datasets   │               │
│  │                 │              │ (no DB record)  │               │
│  │ "Enter title"   │              └─────────────────┘               │
│  └────────┬────────┘                                                 │
│           │ Submit (title ≥ 3 chars)                                 │
│           ↓                                                          │
│  ┌─────────────────┐                                                 │
│  │ POST /datasets  │ ← Dataset created with real title               │
│  │ { title: "..." }│                                                 │
│  └────────┬────────┘                                                 │
│           ↓                                                          │
│  ┌─────────────────┐                                                 │
│  │ Upload Form     │ ← Files uploaded, form completed                │
│  │ (title prefill) │                                                 │
│  └────────┬────────┘                                                 │
│           ↓                                                          │
│  ┌─────────────────┐                                                 │
│  │ Publish Version │                                                 │
│  └─────────────────┘                                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         Backend (Gatekeeper)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐                                                 │
│  │ External Cron   │  Daily at 3 AM                                  │
│  │ or K8s CronJob  │ ────────────────────┐                           │
│  └─────────────────┘                     │                           │
│                                          ↓                           │
│                            ┌─────────────────────────┐               │
│                            │ POST /internal/cleanup/ │               │
│                            │ abandoned-datasets      │               │
│                            └───────────┬─────────────┘               │
│                                        │                             │
│                                        ↓                             │
│                            ┌─────────────────────────┐               │
│                            │    CleanupService       │               │
│                            │                         │               │
│                            │ - Finds DRAFT datasets  │               │
│                            │ - No files              │               │
│                            │ - No DOI                │               │
│                            │ - Inactive 3+ days      │               │
│                            └───────────┬─────────────┘               │
│                                        │                             │
│                                        ↓                             │
│                            ┌─────────────────────────┐               │
│                            │   DatasetRepository     │               │
│                            │                         │               │
│                            │ - fetch_abandoned_...   │               │
│                            │ - hard_delete_dataset   │               │
│                            └───────────┬─────────────┘               │
│                                        │                             │
│                                        ↓                             │
│                            ┌─────────────────────────┐               │
│                            │      PostgreSQL         │               │
│                            │                         │               │
│                            │ DELETE FROM datasets    │               │
│                            │ WHERE ...               │               │
│                            └─────────────────────────┘               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| User creates dataset, adds files, never publishes | **NOT deleted** - has files |
| User enters title, no files, returns in 2 days | **Safe** - within 3-day window |
| User enters title, no files, returns after 4 days | **Deleted** - exceeded inactivity window |
| Cleanup runs while user is uploading files | **Safe** - `updated_at` is recent from dataset creation |
| Dataset has DOI but no files | **NOT deleted** - has DOI |
| User clicks Cancel on title modal | **No dataset created** - clean exit |
| Network error during title submission | **Error shown** - user can retry |

## Configuration

| Parameter | Value | Location | Description |
|-----------|-------|----------|-------------|
| `days_inactive` | 3 | `CleanupService.__init__` | Days of inactivity before cleanup |
| Min title length | 3 | Frontend validation | Minimum characters for title |
| Cleanup schedule | Daily 3 AM | External cron | When cleanup job runs |

## Testing

### Unit Tests

Create `gatekeeper/app/service/cleanup_test.py`:

```python
import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from uuid import uuid4

from app.service.cleanup import CleanupService


class TestCleanupService(unittest.TestCase):
    def setUp(self):
        self.mock_repository = Mock()
        self.service = CleanupService(
            dataset_repository=self.mock_repository,
            days_inactive=3,
        )

    def test_cleanup_deletes_abandoned_datasets(self):
        # Arrange
        mock_dataset = MagicMock()
        mock_dataset.id = uuid4()
        mock_dataset.name = "Abandoned Dataset"
        mock_dataset.created_at = datetime.utcnow() - timedelta(days=5)
        mock_dataset.updated_at = datetime.utcnow() - timedelta(days=5)

        self.mock_repository.fetch_abandoned_empty_datasets.return_value = [mock_dataset]
        self.mock_repository.hard_delete_dataset.return_value = True

        # Act
        result = self.service.cleanup_abandoned_empty_datasets()

        # Assert
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["failed"], 0)
        self.mock_repository.hard_delete_dataset.assert_called_once_with(mock_dataset.id)

    def test_cleanup_with_no_abandoned_datasets(self):
        # Arrange
        self.mock_repository.fetch_abandoned_empty_datasets.return_value = []

        # Act
        result = self.service.cleanup_abandoned_empty_datasets()

        # Assert
        self.assertEqual(result["found"], 0)
        self.assertEqual(result["deleted"], 0)
        self.mock_repository.hard_delete_dataset.assert_not_called()

    def test_cleanup_handles_delete_failure(self):
        # Arrange
        mock_dataset = MagicMock()
        mock_dataset.id = uuid4()
        mock_dataset.name = ""
        mock_dataset.created_at = datetime.utcnow() - timedelta(days=5)
        mock_dataset.updated_at = datetime.utcnow() - timedelta(days=5)

        self.mock_repository.fetch_abandoned_empty_datasets.return_value = [mock_dataset]
        self.mock_repository.hard_delete_dataset.side_effect = Exception("DB error")

        # Act
        result = self.service.cleanup_abandoned_empty_datasets()

        # Assert
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["failed"], 1)
```

### Integration Tests

Add to integration test suite:

1. Create a DRAFT dataset with no files via API
2. Manually set `updated_at` to 4 days ago
3. Call `POST /internal/cleanup/abandoned-datasets`
4. Verify dataset no longer exists
5. Create a DRAFT dataset WITH files
6. Set `updated_at` to 4 days ago
7. Call cleanup endpoint
8. Verify dataset still exists (has files)

### Frontend Tests

1. Navigate to `/app/datasets/new`
2. Verify modal appears with title input
3. Click Cancel → verify redirect to `/app/datasets`, no API call made
4. Enter 2-char title → verify validation error
5. Enter valid title → verify dataset created with that title
6. Verify form appears with title pre-filled

## Deployment

### Phase 1: Frontend (Two-Step Wizard)

1. Deploy frontend changes to staging
2. Test the new flow manually
3. Deploy to production
4. **Immediate effect**: New empty datasets stop being created

### Phase 2: Backend (Cleanup Job)

1. Deploy backend changes (service, repository, endpoint)
2. Run manual cleanup of existing empty datasets:
   ```bash
   curl -X POST https://gatekeeper.internal/internal/cleanup/abandoned-datasets
   ```
3. Review logs and verify correct datasets deleted
4. Set up cron job or K8s CronJob for daily execution:
   ```yaml
   # Kubernetes CronJob example
   apiVersion: batch/v1
   kind: CronJob
   metadata:
     name: cleanup-abandoned-datasets
   spec:
     schedule: "0 3 * * *"  # Daily at 3 AM
     jobTemplate:
       spec:
         template:
           spec:
             containers:
             - name: cleanup
               image: curlimages/curl
               command:
               - curl
               - -X
               - POST
               - http://gatekeeper:9092/internal/cleanup/abandoned-datasets
             restartPolicy: OnFailure
   ```

## Monitoring

### Logs

The cleanup service logs:
- Start of cleanup with configuration
- Each dataset being deleted (id, name, created_at)
- Any failures with stack traces
- Final summary statistics

### Metrics (Future)

Consider adding:
- `datamap_cleanup_datasets_found` - gauge of abandoned datasets per run
- `datamap_cleanup_datasets_deleted` - counter of deleted datasets
- `datamap_cleanup_duration_seconds` - histogram of job duration

## Alternatives Considered

### 1. Soft Delete Instead of Hard Delete

**Pros**: Recoverable, auditable
**Cons**: Doesn't actually reduce database size, still clutters queries

**Decision**: Hard delete for truly empty datasets (no files, no DOI) since there's nothing to recover.

### 2. Deferred Dataset Creation (Create on First File Upload)

**Pros**: No empty datasets ever created
**Cons**:
- Significant refactoring of TUS hooks
- Need temporary upload session concept
- More complex error handling

**Decision**: Two-step wizard is simpler and achieves 90% of the benefit.

### 3. Confirmation Dialog Only

**Pros**: Minimal change
**Cons**: Users still click through, just adds friction

**Decision**: Combined with cleanup job for defense in depth.

### 4. Time-Based Auto-Publish

**Pros**: Converts drafts to published automatically
**Cons**: Publishing empty datasets is worse than leaving them as drafts

**Decision**: Rejected - publishing should be intentional.

## Future Improvements

1. **Email Notification**: Warn users 24 hours before their draft will be deleted
2. **Draft Recovery**: Allow users to recover recently deleted drafts (soft delete for 7 days before hard delete)
3. **Analytics Dashboard**: Show cleanup statistics over time
4. **Configurable Retention**: Per-tenant configuration of cleanup thresholds
5. **Cleanup for Disabled Datasets**: Separate job to hard-delete long-disabled datasets

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `datamap-webapp/pages/app/datasets/new.tsx` | Modify | Add title modal, remove auto-create |
| `gatekeeper/app/repository/dataset.py` | Modify | Add query and delete methods |
| `gatekeeper/app/service/cleanup.py` | Create | New cleanup service |
| `gatekeeper/app/service/cleanup_test.py` | Create | Unit tests |
| `gatekeeper/app/controller/v1/internal/cleanup.py` | Create | Internal endpoint |
| `gatekeeper/app/controller/v1/internal/__init__.py` | Modify | Register router |
| `gatekeeper/app/container.py` | Modify | Register service |

## References

- [Original Issue: Empty datasets accumulating](#)
- [TUS Protocol Documentation](https://tus.io/protocols/resumable-upload.html)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
