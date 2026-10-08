# Notebooks — SDK Implementation Plan (03)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Where the code goes.** A new repository, **`datamap-sdk`**, at `/Users/caio.maia/workspace/datamap/datamap-sdk`, with two packages: `python/` (the `datamap` package on PyPI) and `r/` (the `datamap` R package, installed from a GitHub release). Task 1 creates the repository. Paths below are relative to its root.

**Goal:** Give a notebook session the library the RFC's first cell imports: `datamap.open()` returns the pinned dataset with its metadata and files on their local paths, `datamap.open("id", version="v")` any other dataset the user can read, and two conveniences for the common Python case. The R package does the same without the conveniences. Both are thin on purpose: they answer "what is this dataset and where are its files" and get out of the way of xarray, pandas, ncdf4 or whatever the researcher uses on a path.

**Architecture:** Every call goes to the gatekeeper with the session token as a bearer, on the three dataset read routes the token may reach. `local` is decided by looking at the disk: a file is local when `/data/{dataset_id}/{version_name}/{name}` exists, which is exactly the selection the entrypoint copied. There is no second data path: a file that is not local has no path, and `ds.path(name)` says so. Outside a session the library refuses to open anything, because the only credential that exists today is the session token; the personal token, `datamap.login()` and `ds.download()` are RFC 010 and its own plan, and `open()` already has the parameters they will use.

**Tech Stack:** Python ≥ 3.10, `requests`; optional extras `xarray`, `pandas`; pytest with `responses`; ruff. R ≥ 4.1, `httr2`, `jsonlite`; testthat. GitHub Actions; PyPI trusted publishing; GitHub releases for R.

**Spec:** `docs/rfcs/007-notebooks.md` (§SDK surface). **Contracts:** gatekeeper `docs/superpowers/plans/2026-10-04-notebooks-00-contracts.md` (*Container environment*, *Session token*, the bearer routes) — wins over this plan on any interface.

## Global Constraints

- Environment the session provides, read exactly: `DATAMAP_API_URL`, `DATAMAP_SESSION_TOKEN`, `DATAMAP_DATASETS` (JSON list of `{"id", "version"}`), `DATAMAP_NOTEBOOK_ID`.
- Routes used, exactly: `GET {api}/datasets/{id}` and `GET {api}/datasets/{id}/versions/{version_name}`, with `Authorization: Bearer {token}`. Nothing else: the token reaches nothing else, and the SDK must not try.
- Local path: `/data/{dataset_id}/{version_name}/{file name}`; `local` is `os.path.isfile` of that path. The mount root is a module constant `DATA_MOUNT = "/data"` overridable only for tests.
- Errors: `datamap.DataMapError(status_code, detail)` for any non-2xx; `datamap.NotInSession` when the environment is missing; `datamap.FileNotMounted(name)` from `path()` when a file is not local; `datamap.UnknownFile(name)` when it is not in the version at all.
- Metadata (`ds.meta`): `title`, `description`, `license`, `doi`, `version`, `tenancy`, `created_at`, plus the raw `data` dict. Everything comes from the two routes above; the library invents nothing.
- Python conveniences: `ds.open_mfdataset(pattern="*.nc", **kwargs)` → `xarray.open_mfdataset` over the matching local paths (imports xarray lazily; raises `ImportError` with an install hint); `ds.read_csv(name, **kwargs)` → `pandas.read_csv` on the local path. Both refuse a file that is not local with `FileNotMounted`.
- The first cell the entrypoint writes is `import datamap`, `ds = datamap.open()`, `ds.files` (Python) and `library(datamap)`, `ds <- datamap::open()`, `ds$files` (R). `ds.files` must therefore print well: a `FileList` whose `__repr__` is the table the design shows (`<Dataset 3f9c1e v2 · 14 files · 2.3 GB>` then one line per file, name, size, type, and `not mounted` where it is not).
- No comments narrating code; type hints everywhere; `ruff check` and `ruff format --check` clean (ruff 0.5.x, line length 88).
- Versions: Python `0.1.0`, R `0.1.0`; tags `v0.1.0` (PyPI) and `r-0.1.0` (R release). The notebook image (plan 02) pins both.

## File Structure

| File | Responsibility |
|---|---|
| `README.md`, `LICENSE`, `.gitignore` | the repository |
| `python/pyproject.toml`, `python/README.md` | packaging |
| `python/src/datamap/__init__.py` | public names: `open`, `Dataset`, `File`, `FileList`, errors, `__version__` |
| `python/src/datamap/errors.py` | the four exceptions |
| `python/src/datamap/session.py` | `Session.from_env()`, `Session.current()` |
| `python/src/datamap/client.py` | `GatekeeperClient.get(path) -> dict` with the bearer, errors mapped |
| `python/src/datamap/dataset.py` | `File`, `FileList`, `Dataset`, `open()`, `_human_size` |
| `python/src/datamap/convenience.py` | `open_mfdataset`, `read_csv` |
| `python/tests/conftest.py`, `test_session.py`, `test_client.py`, `test_dataset.py`, `test_convenience.py`, `test_public_api.py` | tests |
| `r/DESCRIPTION`, `r/NAMESPACE`, `r/R/session.R`, `r/R/client.R`, `r/R/open.R`, `r/tests/testthat.R`, `r/tests/testthat/test-open.R`, `r/README.md` | the R package |
| `.github/workflows/ci.yml`, `.github/workflows/release.yml` | tests on every push; publish on tags |

---

### Task 1: The repository and the Python package skeleton

**Files:**
- Create: `README.md`, `LICENSE`, `.gitignore`, `python/pyproject.toml`, `python/README.md`, `python/src/datamap/__init__.py`, `python/src/datamap/errors.py`, `python/tests/conftest.py`, `python/tests/test_public_api.py`

- [ ] **Step 1: Create the repository**

```bash
mkdir -p /Users/caio.maia/workspace/datamap/datamap-sdk && cd /Users/caio.maia/workspace/datamap/datamap-sdk
git init -b main
mkdir -p python/src/datamap python/tests r/R r/tests/testthat .github/workflows
```

`.gitignore`:

```
__pycache__/
*.pyc
.venv/
dist/
build/
*.egg-info/
.pytest_cache/
.ruff_cache/
r/.Rhistory
r/*.Rcheck/
r/*.tar.gz
```

`LICENSE`: the licence the other DataMap repositories use (check `gatekeeper/LICENSE`; copy it).

`README.md`:

```markdown
# datamap-sdk

The `datamap` library that a DataMap notebook session has pre-loaded, in Python
(`python/`) and in R (`r/`). It answers "what is this dataset and where are its
files" and gets out of the way of the libraries you already use on a path.

```python
import datamap
ds = datamap.open()            # this notebook's dataset, pinned to its version
ds.files                       # the files, with their local paths
ds.open_mfdataset("*.nc")      # xarray over the local NetCDF files
```

```r
library(datamap)
ds <- datamap::open()
ds$files
ncdf4::nc_open(ds$path("t3_smps_20140201_20140228.nc"))
```

Outside a DataMap session there is no credential to use yet, and `open()`
says so. The design is RFC 007 in the gatekeeper repository.
```

- [ ] **Step 2: Packaging**

`python/pyproject.toml`:

```toml
[project]
name = "datamap"
version = "0.1.0"
description = "The DataMap library a notebook session has pre-loaded"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
dependencies = ["requests>=2.31,<3"]

[project.optional-dependencies]
xarray = ["xarray>=2023.1", "h5netcdf>=1.0", "netcdf4>=1.6"]
pandas = ["pandas>=2.0"]
dev = ["pytest>=8.0", "responses>=0.25", "ruff>=0.5,<0.6", "pandas>=2.0", "xarray>=2023.1"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 88
target-version = "py310"
```

(If the licence file is not MIT, change `license` to match.)

`python/README.md`: the Python half of the root README, plus `pip install datamap[xarray,pandas]`.

- [ ] **Step 3: Failing public-API test**

`python/tests/test_public_api.py`:

```python
import datamap


def test_the_public_names_exist():
    for name in ("open", "Dataset", "File", "FileList", "DataMapError", "NotInSession", "FileNotMounted", "UnknownFile", "__version__"):
        assert hasattr(datamap, name), name


def test_the_version_matches_pyproject():
    assert datamap.__version__ == "0.1.0"
```

Run: `cd python && python -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest -q`
Expected: FAIL (`AttributeError` on the missing names)

- [ ] **Step 4: Errors and the package root**

`python/src/datamap/errors.py`:

```python
class DataMapError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class NotInSession(Exception):
    pass


class UnknownFile(KeyError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"no file named {self.name!r} in this version"


class FileNotMounted(FileNotFoundError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return (
            f"{self.name!r} is not mounted in this session; change the notebook's "
            "file selection on its page and restart the session"
        )
```

`python/src/datamap/__init__.py` (the `Dataset`, `File`, `FileList` and `open` names come from Task 3; import them there):

```python
from datamap.dataset import Dataset, File, FileList, open
from datamap.errors import DataMapError, FileNotMounted, NotInSession, UnknownFile

__version__ = "0.1.0"

__all__ = [
    "open",
    "Dataset",
    "File",
    "FileList",
    "DataMapError",
    "FileNotMounted",
    "NotInSession",
    "UnknownFile",
    "__version__",
]
```

Until Task 3 exists, create `python/src/datamap/dataset.py` with four placeholders so the package imports:

```python
class File: ...
class FileList: ...
class Dataset: ...
def open(*args, **kwargs): ...
```

Task 3 replaces the file entirely.

`python/tests/conftest.py`:

```python
import os

import pytest


@pytest.fixture
def session_env(monkeypatch):
    monkeypatch.setenv("DATAMAP_API_URL", "http://gatekeeper:9092/api/v1")
    monkeypatch.setenv("DATAMAP_SESSION_TOKEN", "tok")
    monkeypatch.setenv("DATAMAP_NOTEBOOK_ID", "nb-1")
    monkeypatch.setenv("DATAMAP_DATASETS", '[{"id": "ds-1", "version": "2"}]')


@pytest.fixture
def no_session_env(monkeypatch):
    for name in ("DATAMAP_API_URL", "DATAMAP_SESSION_TOKEN", "DATAMAP_NOTEBOOK_ID", "DATAMAP_DATASETS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def data_mount(tmp_path, monkeypatch):
    from datamap import dataset

    monkeypatch.setattr(dataset, "DATA_MOUNT", str(tmp_path))
    return tmp_path
```

Run the tests. Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: datamap-sdk repository, Python package skeleton"
```

---

### Task 2: Session and client

**Files:**
- Create: `python/src/datamap/session.py`, `python/src/datamap/client.py`
- Create: `python/tests/test_session.py`, `python/tests/test_client.py`

**Interfaces:**
- Produces: `Session(api_url: str, token: str, notebook_id: str | None, datasets: list[dict])`, `Session.from_env(environ=os.environ) -> Session` (raises `NotInSession`), `Session.pinned() -> tuple[str, str]` (id, version of `datasets[0]`); `GatekeeperClient(session)` with `get(path: str) -> dict` (raises `DataMapError`).

- [ ] **Step 1: Failing tests**

`python/tests/test_session.py`:

```python
import pytest

from datamap.errors import NotInSession
from datamap.session import Session


def test_from_env_reads_the_four_variables(session_env):
    session = Session.from_env()

    assert session.api_url == "http://gatekeeper:9092/api/v1"
    assert session.token == "tok"
    assert session.notebook_id == "nb-1"
    assert session.pinned() == ("ds-1", "2")


def test_a_trailing_slash_on_the_api_url_is_dropped(session_env, monkeypatch):
    monkeypatch.setenv("DATAMAP_API_URL", "http://g/api/v1/")

    assert Session.from_env().api_url == "http://g/api/v1"


def test_outside_a_session_says_so(no_session_env):
    with pytest.raises(NotInSession) as raised:
        Session.from_env()
    assert "DataMap notebook session" in str(raised.value)


def test_a_session_without_datasets_has_nothing_pinned(session_env, monkeypatch):
    monkeypatch.setenv("DATAMAP_DATASETS", "[]")

    with pytest.raises(NotInSession):
        Session.from_env().pinned()
```

`python/tests/test_client.py`:

```python
import pytest
import responses

from datamap.client import GatekeeperClient
from datamap.errors import DataMapError
from datamap.session import Session

API = "http://gatekeeper:9092/api/v1"


@pytest.fixture
def client():
    return GatekeeperClient(Session(api_url=API, token="tok", notebook_id="nb", datasets=[]))


@responses.activate
def test_get_sends_the_bearer_and_returns_json(client):
    responses.get(f"{API}/datasets/ds-1", json={"id": "ds-1"})

    assert client.get("/datasets/ds-1") == {"id": "ds-1"}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"
    assert responses.calls[0].request.headers["Accept"] == "application/json"


@responses.activate
def test_a_404_becomes_a_datamap_error_with_the_detail(client):
    responses.get(f"{API}/datasets/ds-9", json={"detail": "not_found: ds-9"}, status=404)

    with pytest.raises(DataMapError) as raised:
        client.get("/datasets/ds-9")
    assert raised.value.status_code == 404
    assert raised.value.detail == "not_found: ds-9"


@responses.activate
def test_a_401_explains_the_session(client):
    responses.get(f"{API}/datasets/ds-1", json={"detail": "Unauthorized"}, status=401)

    with pytest.raises(DataMapError) as raised:
        client.get("/datasets/ds-1")
    assert "session" in raised.value.detail


@responses.activate
def test_a_body_that_is_not_json_still_becomes_an_error(client):
    responses.get(f"{API}/datasets/ds-1", body="<html>bad gateway</html>", status=502)

    with pytest.raises(DataMapError) as raised:
        client.get("/datasets/ds-1")
    assert raised.value.status_code == 502
```

Run: `.venv/bin/python -m pytest tests/test_session.py tests/test_client.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Write them**

`python/src/datamap/session.py`:

```python
import json
import os
from dataclasses import dataclass, field

from datamap.errors import NotInSession

HINT = (
    "datamap.open() needs a DataMap notebook session: open the notebook from "
    "DataMap, or pass api_url= and token= explicitly"
)


@dataclass(frozen=True)
class Session:
    api_url: str
    token: str
    notebook_id: str | None = None
    datasets: list[dict] = field(default_factory=list)

    @classmethod
    def from_env(cls, environ=os.environ) -> "Session":
        api_url = environ.get("DATAMAP_API_URL")
        token = environ.get("DATAMAP_SESSION_TOKEN")
        if not api_url or not token:
            raise NotInSession(HINT)
        try:
            datasets = json.loads(environ.get("DATAMAP_DATASETS") or "[]")
        except ValueError:
            datasets = []
        return cls(
            api_url=api_url.rstrip("/"),
            token=token,
            notebook_id=environ.get("DATAMAP_NOTEBOOK_ID") or None,
            datasets=list(datasets),
        )

    def pinned(self) -> tuple[str, str]:
        if not self.datasets:
            raise NotInSession("this session has no dataset pinned; pass a dataset id")
        first = self.datasets[0]
        return str(first["id"]), str(first["version"])
```

`python/src/datamap/client.py`:

```python
import requests

from datamap.errors import DataMapError
from datamap.session import Session

TIMEOUT = (5, 60)
UNAUTHORIZED_HINT = "the session token was refused: the session may have ended; reopen the notebook from DataMap"


class GatekeeperClient:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._http = requests.Session()
        self._http.headers.update(
            {"Authorization": f"Bearer {session.token}", "Accept": "application/json"}
        )

    def get(self, path: str) -> dict:
        response = self._http.get(f"{self._session.api_url}{path}", timeout=TIMEOUT)
        if response.status_code >= 400:
            raise DataMapError(response.status_code, _detail(response))
        return response.json()


def _detail(response: requests.Response) -> str:
    if response.status_code == 401:
        return UNAUTHORIZED_HINT
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail) if detail else str(body)[:200]
```

Run the tests. Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add python
git commit -m "feat(python): session from the environment, client with the bearer

Outside a session there is nothing to authenticate with, and the error says
so instead of failing on a missing header later."
```

---

### Task 3: `Dataset`, `File`, `FileList`, `open()`

**Files:**
- Replace: `python/src/datamap/dataset.py`
- Create: `python/tests/test_dataset.py`

**Interfaces:**
- Produces: `File(id, name, size_bytes, type, local, path)`; `FileList(list[File])` with `names`, `local`, `__getitem__` by name, `glob(pattern)`, `__repr__`; `Dataset(id, version_name, meta: dict, files: FileList, mount_path)` with `path(name) -> str`, `open_mfdataset`, `read_csv` (Task 4); `open(dataset_id: str | None = None, version: str | None = None, *, api_url: str | None = None, token: str | None = None) -> Dataset`; `DATA_MOUNT`.

- [ ] **Step 1: Failing tests**

`python/tests/test_dataset.py`:

```python
import pytest
import responses

import datamap
from datamap.errors import DataMapError, FileNotMounted, UnknownFile

API = "http://gatekeeper:9092/api/v1"

DATASET = {
    "id": "ds-1",
    "name": "GoAmazon 2014/5 — Aerosol size distribution, T3 site",
    "tenancy": "datamap/production/data-amazon",
    "created_at": "2024-03-11T10:00:00+00:00",
    "data": {"description": "SMPS at T3", "license": "CC BY 4.0", "institution": "USP"},
}

VERSION = {
    "id": "v-2",
    "name": "2",
    "doi": {"identifier": "10.5281/datamap.3f9c1e", "state": "FINDABLE"},
    "files_in": [
        {"id": "f-a", "name": "t3_smps_20140201_20140228.nc", "size_bytes": 176160768, "extension": "nc", "format": "application/x-netcdf"},
        {"id": "f-b", "name": "quality_flags/flags.csv", "size_bytes": 2100000, "extension": "csv", "format": "text/csv"},
        {"id": "f-c", "name": "README.md", "size_bytes": 6000, "extension": "md", "format": "text/markdown"},
    ],
}


def stub_dataset(dataset=DATASET, version=VERSION):
    responses.get(f"{API}/datasets/{dataset['id']}", json=dataset)
    responses.get(f"{API}/datasets/{dataset['id']}/versions/{version['name']}", json={"version": version, **dataset})


def mount(data_mount, *names):
    for name in names:
        path = data_mount / "ds-1" / "2" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


@responses.activate
def test_open_with_no_argument_is_the_pinned_dataset(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "t3_smps_20140201_20140228.nc", "quality_flags/flags.csv", "README.md")

    ds = datamap.open()

    assert ds.id == "ds-1"
    assert ds.version_name == "2"
    assert ds.mount_path == f"{data_mount}/ds-1/2"
    assert len(ds.files) == 3
    assert all(f.local for f in ds.files)
    assert ds.path("quality_flags/flags.csv") == f"{data_mount}/ds-1/2/quality_flags/flags.csv"


@responses.activate
def test_meta_comes_from_the_two_routes(session_env, data_mount):
    stub_dataset()

    meta = datamap.open().meta

    assert meta["title"] == DATASET["name"]
    assert meta["description"] == "SMPS at T3"
    assert meta["license"] == "CC BY 4.0"
    assert meta["doi"] == "10.5281/datamap.3f9c1e"
    assert meta["version"] == "2"
    assert meta["tenancy"] == "datamap/production/data-amazon"
    assert meta["data"]["institution"] == "USP"


@responses.activate
def test_a_file_outside_the_selection_is_not_local_and_has_no_path(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "README.md")

    ds = datamap.open()

    assert ds.files["README.md"].local is True
    assert ds.files["t3_smps_20140201_20140228.nc"].local is False
    assert ds.files["t3_smps_20140201_20140228.nc"].path is None
    with pytest.raises(FileNotMounted):
        ds.path("t3_smps_20140201_20140228.nc")


@responses.activate
def test_an_unknown_name_is_distinct_from_an_unmounted_one(session_env, data_mount):
    stub_dataset()

    with pytest.raises(UnknownFile):
        datamap.open().path("nope.nc")


@responses.activate
def test_open_another_dataset_lists_it_with_nothing_local(session_env, data_mount):
    other = dict(DATASET, id="ds-7", name="Other")
    version = dict(VERSION, name="4")
    stub_dataset(other, version)

    ds = datamap.open("ds-7", version="4")

    assert ds.id == "ds-7"
    assert ds.version_name == "4"
    assert not any(f.local for f in ds.files)


@responses.activate
def test_open_another_dataset_needs_a_version(session_env, data_mount):
    with pytest.raises(ValueError):
        datamap.open("ds-7")


@responses.activate
def test_a_dataset_the_user_cannot_read_is_an_error_with_the_status(session_env, data_mount):
    responses.get(f"{API}/datasets/ds-9", json={"detail": "not_found: ds-9"}, status=404)

    with pytest.raises(DataMapError) as raised:
        datamap.open("ds-9", version="1")
    assert raised.value.status_code == 404


def test_open_outside_a_session_says_so(no_session_env):
    with pytest.raises(datamap.NotInSession):
        datamap.open()


@responses.activate
def test_explicit_credentials_bypass_the_environment(no_session_env, data_mount):
    stub_dataset()

    ds = datamap.open("ds-1", version="2", api_url=API, token="tok")

    assert ds.id == "ds-1"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_files_glob_and_repr(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "t3_smps_20140201_20140228.nc", "README.md")

    ds = datamap.open()

    assert ds.files.glob("*.nc").names == ["t3_smps_20140201_20140228.nc"]
    text = repr(ds.files)
    assert text.startswith("<Dataset ds-1 v2 · 3 files · 174.1 MB>")
    assert "quality_flags/flags.csv" in text and "not mounted" in text
    assert "README.md" in text
```

Run: `.venv/bin/python -m pytest tests/test_dataset.py -q`
Expected: FAIL (`AttributeError` or `TypeError` from the placeholders)

- [ ] **Step 2: Write `dataset.py`**

```python
import fnmatch
import os
from dataclasses import dataclass

from datamap.client import GatekeeperClient
from datamap.errors import FileNotMounted, UnknownFile
from datamap.session import Session

DATA_MOUNT = "/data"


@dataclass(frozen=True)
class File:
    id: str
    name: str
    size_bytes: int
    type: str | None
    local: bool
    path: str | None


class FileList(list):
    def __init__(self, files: list[File], dataset_id: str, version_name: str) -> None:
        super().__init__(files)
        self._dataset_id = dataset_id
        self._version_name = version_name

    @property
    def names(self) -> list[str]:
        return [f.name for f in self]

    @property
    def local(self) -> "FileList":
        return FileList([f for f in self if f.local], self._dataset_id, self._version_name)

    def glob(self, pattern: str) -> "FileList":
        return FileList(
            [f for f in self if fnmatch.fnmatch(f.name, pattern)],
            self._dataset_id,
            self._version_name,
        )

    def __getitem__(self, key):
        if isinstance(key, str):
            for f in self:
                if f.name == key:
                    return f
            raise UnknownFile(key)
        return super().__getitem__(key)

    def __repr__(self) -> str:
        total = sum(f.size_bytes for f in self)
        lines = [
            f"<Dataset {self._dataset_id} v{self._version_name} · {len(self)} files · {_human_size(total)}>"
        ]
        width = max((len(f.name) for f in self), default=0)
        for f in self:
            note = "" if f.local else "   not mounted"
            lines.append(
                f"  {f.name.ljust(width)}  {_human_size(f.size_bytes).rjust(9)}  {f.type or ''}{note}"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class Dataset:
    id: str
    version_name: str
    meta: dict
    files: FileList
    mount_path: str

    def path(self, name: str) -> str:
        file = self.files[name]
        if not file.local or file.path is None:
            raise FileNotMounted(name)
        return file.path

    def open_mfdataset(self, pattern: str = "*.nc", **kwargs):
        from datamap.convenience import open_mfdataset

        return open_mfdataset(self, pattern, **kwargs)

    def read_csv(self, name: str, **kwargs):
        from datamap.convenience import read_csv

        return read_csv(self, name, **kwargs)

    def __repr__(self) -> str:
        return f"<Dataset {self.id} v{self.version_name} · {self.meta.get('title')!r}>"


def open(
    dataset_id: str | None = None,
    version: str | None = None,
    *,
    api_url: str | None = None,
    token: str | None = None,
) -> Dataset:
    if api_url and token:
        session = Session(api_url=api_url.rstrip("/"), token=token)
    else:
        session = Session.from_env()
    if dataset_id is None:
        dataset_id, version = session.pinned()
    elif version is None:
        raise ValueError("version= is required when opening another dataset")
    client = GatekeeperClient(session)
    dataset = client.get(f"/datasets/{dataset_id}")
    detail = client.get(f"/datasets/{dataset_id}/versions/{version}")
    version_body = detail.get("version") or detail
    mount_path = os.path.join(DATA_MOUNT, dataset_id, version)
    files = FileList(
        [_file(entry, mount_path) for entry in version_body.get("files_in") or []],
        dataset_id,
        version,
    )
    return Dataset(
        id=dataset_id,
        version_name=version,
        meta=_meta(dataset, version_body),
        files=files,
        mount_path=mount_path,
    )


def _file(entry: dict, mount_path: str) -> File:
    name = entry["name"]
    path = os.path.join(mount_path, name)
    local = os.path.isfile(path)
    return File(
        id=str(entry["id"]),
        name=name,
        size_bytes=int(entry.get("size_bytes") or 0),
        type=entry.get("extension") or entry.get("format"),
        local=local,
        path=path if local else None,
    )


def _meta(dataset: dict, version: dict) -> dict:
    data = dataset.get("data") or {}
    doi = version.get("doi") or {}
    return {
        "title": dataset.get("name"),
        "description": data.get("description"),
        "license": data.get("license"),
        "doi": doi.get("identifier"),
        "version": version.get("name"),
        "tenancy": dataset.get("tenancy"),
        "created_at": dataset.get("created_at"),
        "data": data,
    }


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
```

The version route's response wraps the version under `version` next to the dataset fields (`DatasetVersionGetResponse` in the gatekeeper); `detail.get("version") or detail` covers both that shape and a bare version. Confirm once against a running gatekeeper (`curl .../datasets/{id}/versions/{v}` with the integration headers) and remove the fallback if the shape is the wrapped one.

Run: `.venv/bin/python -m pytest -q`
Expected: all passed (the convenience methods import lazily and are not exercised yet)

- [ ] **Step 3: Commit**

```bash
git add python
git commit -m "feat(python): open(), Dataset, File and a FileList that prints like the design

local is decided by the disk: a file is local when its path under /data
exists, which is exactly what the entrypoint copied. A file that is not
local has no path, and path() says why."
```

---

### Task 4: Conveniences

**Files:**
- Create: `python/src/datamap/convenience.py`, `python/tests/test_convenience.py`

- [ ] **Step 1: Failing tests**

`python/tests/test_convenience.py`:

```python
import sys
from unittest.mock import patch

import pytest
import responses

import datamap
from datamap.errors import FileNotMounted

from tests.test_dataset import API, DATASET, VERSION, mount, stub_dataset  # noqa: F401


@responses.activate
def test_open_mfdataset_passes_the_local_paths_to_xarray(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "t3_smps_20140201_20140228.nc", "quality_flags/flags.csv", "README.md")
    ds = datamap.open()

    with patch("xarray.open_mfdataset") as open_mf:
        ds.open_mfdataset("*.nc", combine="by_coords")

    open_mf.assert_called_once_with(
        [f"{data_mount}/ds-1/2/t3_smps_20140201_20140228.nc"], combine="by_coords"
    )


@responses.activate
def test_open_mfdataset_refuses_when_a_matching_file_is_not_mounted(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "README.md")
    ds = datamap.open()

    with pytest.raises(FileNotMounted):
        ds.open_mfdataset("*.nc")


@responses.activate
def test_open_mfdataset_with_no_match_is_a_value_error(session_env, data_mount):
    stub_dataset()
    ds = datamap.open()

    with pytest.raises(ValueError):
        ds.open_mfdataset("*.zarr")


@responses.activate
def test_read_csv_reads_the_local_path_with_pandas(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "quality_flags/flags.csv")
    (data_mount / "ds-1" / "2" / "quality_flags" / "flags.csv").write_text("a,b\n1,2\n")
    ds = datamap.open()

    frame = ds.read_csv("quality_flags/flags.csv")

    assert list(frame.columns) == ["a", "b"]


@responses.activate
def test_missing_xarray_is_an_import_error_with_a_hint(session_env, data_mount):
    stub_dataset()
    mount(data_mount, "t3_smps_20140201_20140228.nc")
    ds = datamap.open()

    with patch.dict(sys.modules, {"xarray": None}):
        with pytest.raises(ImportError) as raised:
            ds.open_mfdataset()
    assert "pip install" in str(raised.value)
```

Add `python/tests/__init__.py` (empty) so `from tests.test_dataset import ...` resolves with `pythonpath = ["src"]`; if pytest complains, add `"."` to `pythonpath` in `pyproject.toml`.

- [ ] **Step 2: Write `convenience.py`**

```python
from datamap.errors import FileNotMounted


def open_mfdataset(dataset, pattern: str = "*.nc", **kwargs):
    matching = dataset.files.glob(pattern)
    if not matching:
        raise ValueError(f"no file in this version matches {pattern!r}")
    paths = []
    for file in matching:
        if not file.local or file.path is None:
            raise FileNotMounted(file.name)
        paths.append(file.path)
    try:
        import xarray
    except ImportError as error:
        raise ImportError(
            "xarray is not installed: pip install 'datamap[xarray]'"
        ) from error
    return xarray.open_mfdataset(paths, **kwargs)


def read_csv(dataset, name: str, **kwargs):
    path = dataset.path(name)
    try:
        import pandas
    except ImportError as error:
        raise ImportError("pandas is not installed: pip install 'datamap[pandas]'") from error
    return pandas.read_csv(path, **kwargs)
```

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests`
Expected: all passed; no findings

- [ ] **Step 3: Commit**

```bash
git add python
git commit -m "feat(python): open_mfdataset and read_csv over the local paths"
```

---

### Task 5: The R package

**Files:**
- Create: `r/DESCRIPTION`, `r/NAMESPACE`, `r/R/session.R`, `r/R/client.R`, `r/R/open.R`, `r/tests/testthat.R`, `r/tests/testthat/test-open.R`, `r/README.md`

**Interfaces:**
- Produces: `datamap::open(dataset_id = NULL, version = NULL, api_url = NULL, token = NULL)` returning a list of class `datamap_dataset` with `id`, `version_name`, `meta` (list), `files` (data.frame: `id`, `name`, `size_bytes`, `type`, `local`, `path`), `mount_path`, and `path(name)` as a closure; `print.datamap_dataset`.

- [ ] **Step 1: Package metadata**

`r/DESCRIPTION`:

```
Package: datamap
Title: The DataMap Library a Notebook Session Has Pre-Loaded
Version: 0.1.0
Authors@R: person("DataMap Team", email = "datamap@pcs.usp.br", role = c("aut", "cre"))
Description: Opens the dataset a DataMap notebook session is pinned to, with
    its metadata and the local paths of its files.
License: MIT + file LICENSE
Encoding: UTF-8
Depends: R (>= 4.1)
Imports: httr2 (>= 1.0), jsonlite
Suggests: testthat (>= 3.0), webfakes
Config/testthat/edition: 3
RoxygenNote: 7.3.1
```

`r/NAMESPACE`:

```
export(open)
S3method(print, datamap_dataset)
importFrom(httr2, request, req_headers, req_perform, req_error, resp_status, resp_body_json, resp_body_string)
importFrom(jsonlite, fromJSON)
```

`r/LICENSE`: `YEAR: 2026` / `COPYRIGHT HOLDER: DataMap Team` (the two-line form R expects for `MIT + file LICENSE`).

- [ ] **Step 2: Failing test**

`r/tests/testthat.R`:

```r
library(testthat)
library(datamap)
test_check("datamap")
```

`r/tests/testthat/test-open.R`:

```r
dataset_body <- list(
  id = "ds-1",
  name = "GoAmazon T3",
  tenancy = "t",
  created_at = "2024-03-11T10:00:00+00:00",
  data = list(description = "SMPS", license = "CC BY 4.0")
)
version_body <- list(
  version = list(
    name = "2",
    doi = list(identifier = "10.5281/x"),
    files_in = list(
      list(id = "f-a", name = "a.nc", size_bytes = 100, extension = "nc"),
      list(id = "f-b", name = "q/flags.csv", size_bytes = 200, extension = "csv")
    )
  )
)

fake_fetch <- function(path) {
  if (path == "/datasets/ds-1") return(dataset_body)
  if (path == "/datasets/ds-1/versions/2") return(version_body)
  stop(datamap:::datamap_error(404, paste("not_found:", path)))
}

with_session <- function(code, mount) {
  withr::local_envvar(
    DATAMAP_API_URL = "http://g/api/v1",
    DATAMAP_SESSION_TOKEN = "tok",
    DATAMAP_DATASETS = '[{"id":"ds-1","version":"2"}]'
  )
  withr::local_options(datamap.data_mount = mount, datamap.fetch = fake_fetch)
  force(code)
}

test_that("open() returns the pinned dataset with local paths where files exist", {
  mount <- withr::local_tempdir()
  dir.create(file.path(mount, "ds-1", "2"), recursive = TRUE)
  writeLines("x", file.path(mount, "ds-1", "2", "a.nc"))

  ds <- with_session(datamap::open(), mount)

  expect_equal(ds$id, "ds-1")
  expect_equal(ds$version_name, "2")
  expect_equal(ds$meta$title, "GoAmazon T3")
  expect_equal(ds$meta$doi, "10.5281/x")
  expect_equal(nrow(ds$files), 2)
  expect_true(ds$files$local[ds$files$name == "a.nc"])
  expect_false(ds$files$local[ds$files$name == "q/flags.csv"])
  expect_equal(ds$path("a.nc"), file.path(mount, "ds-1", "2", "a.nc"))
})

test_that("path() of a file that is not mounted errors with the reason", {
  mount <- withr::local_tempdir()
  ds <- with_session(datamap::open(), mount)

  expect_error(ds$path("q/flags.csv"), "not mounted")
  expect_error(ds$path("nope.nc"), "no file named")
})

test_that("open() outside a session says so", {
  withr::local_envvar(DATAMAP_API_URL = NA, DATAMAP_SESSION_TOKEN = NA, DATAMAP_DATASETS = NA)

  expect_error(datamap::open(), "DataMap notebook session")
})

test_that("another dataset needs a version", {
  mount <- withr::local_tempdir()
  expect_error(with_session(datamap::open("ds-7"), mount), "version")
})

test_that("print shows the header and marks unmounted files", {
  mount <- withr::local_tempdir()
  ds <- with_session(datamap::open(), mount)

  out <- capture.output(print(ds))

  expect_match(out[1], "<Dataset ds-1 v2 · 2 files")
  expect_true(any(grepl("not mounted", out)))
})
```

Run: `cd r && Rscript -e 'devtools::test()'` (or `R CMD check` later)
Expected: errors, the functions do not exist yet.

- [ ] **Step 3: Write the package**

`r/R/session.R`:

```r
datamap_error <- function(status, detail) {
  structure(
    class = c("datamap_error", "error", "condition"),
    list(message = paste0(status, ": ", detail), status = status, detail = detail, call = NULL)
  )
}

session_from_env <- function(api_url = NULL, token = NULL) {
  api_url <- api_url %||% Sys.getenv("DATAMAP_API_URL", unset = NA)
  token <- token %||% Sys.getenv("DATAMAP_SESSION_TOKEN", unset = NA)
  if (is.na(api_url) || is.na(token) || !nzchar(api_url) || !nzchar(token)) {
    stop("datamap::open() needs a DataMap notebook session: open the notebook from DataMap, or pass api_url and token", call. = FALSE)
  }
  datasets <- Sys.getenv("DATAMAP_DATASETS", unset = "[]")
  datasets <- tryCatch(jsonlite::fromJSON(datasets, simplifyVector = FALSE), error = function(e) list())
  list(api_url = sub("/+$", "", api_url), token = token, datasets = datasets)
}

`%||%` <- function(a, b) if (is.null(a)) b else a
```

`r/R/client.R`:

```r
fetch_json <- function(session, path) {
  override <- getOption("datamap.fetch")
  if (is.function(override)) return(override(path))
  resp <- httr2::request(paste0(session$api_url, path)) |>
    httr2::req_headers(Authorization = paste("Bearer", session$token), Accept = "application/json") |>
    httr2::req_error(is_error = function(resp) FALSE) |>
    httr2::req_perform()
  status <- httr2::resp_status(resp)
  if (status >= 400) {
    detail <- if (status == 401) {
      "the session token was refused: the session may have ended; reopen the notebook from DataMap"
    } else {
      body <- tryCatch(httr2::resp_body_json(resp), error = function(e) NULL)
      if (is.list(body) && !is.null(body$detail)) as.character(body$detail) else httr2::resp_body_string(resp)
    }
    stop(datamap_error(status, detail))
  }
  httr2::resp_body_json(resp, simplifyVector = FALSE)
}
```

`r/R/open.R`:

```r
#' Open a DataMap dataset
#'
#' With no arguments, the dataset this notebook session is pinned to. With a
#' dataset id and a version, any other dataset the user can read; its files
#' are listed but not local.
#' @param dataset_id A dataset id, or NULL for the pinned one.
#' @param version The version name; required with dataset_id.
#' @param api_url,token Explicit credentials instead of the session's.
#' @return A list of class "datamap_dataset".
#' @export
open <- function(dataset_id = NULL, version = NULL, api_url = NULL, token = NULL) {
  session <- session_from_env(api_url, token)
  if (is.null(dataset_id)) {
    if (length(session$datasets) == 0) stop("this session has no dataset pinned; pass a dataset id", call. = FALSE)
    dataset_id <- as.character(session$datasets[[1]]$id)
    version <- as.character(session$datasets[[1]]$version)
  } else if (is.null(version)) {
    stop("version is required when opening another dataset", call. = FALSE)
  }
  dataset <- fetch_json(session, paste0("/datasets/", dataset_id))
  detail <- fetch_json(session, paste0("/datasets/", dataset_id, "/versions/", version))
  version_body <- if (!is.null(detail$version)) detail$version else detail
  mount_path <- file.path(getOption("datamap.data_mount", "/data"), dataset_id, version)
  files <- files_frame(version_body$files_in, mount_path)
  ds <- list(
    id = dataset_id,
    version_name = version,
    meta = meta_of(dataset, version_body),
    files = files,
    mount_path = mount_path
  )
  ds$path <- function(name) {
    row <- files[files$name == name, ]
    if (nrow(row) == 0) stop(sprintf("no file named '%s' in this version", name), call. = FALSE)
    if (!row$local) stop(sprintf("'%s' is not mounted in this session; change the notebook's file selection on its page and restart the session", name), call. = FALSE)
    row$path
  }
  class(ds) <- "datamap_dataset"
  ds
}

files_frame <- function(entries, mount_path) {
  if (length(entries) == 0) {
    return(data.frame(id = character(), name = character(), size_bytes = numeric(), type = character(), local = logical(), path = character(), stringsAsFactors = FALSE))
  }
  name <- vapply(entries, function(e) as.character(e$name), character(1))
  path <- file.path(mount_path, name)
  local <- file.exists(path)
  data.frame(
    id = vapply(entries, function(e) as.character(e$id), character(1)),
    name = name,
    size_bytes = vapply(entries, function(e) as.numeric(e$size_bytes %||% 0), numeric(1)),
    type = vapply(entries, function(e) as.character(e$extension %||% e$format %||% NA), character(1)),
    local = local,
    path = ifelse(local, path, NA_character_),
    stringsAsFactors = FALSE
  )
}

meta_of <- function(dataset, version) {
  data <- dataset$data %||% list()
  list(
    title = dataset$name,
    description = data$description,
    license = data$license,
    doi = version$doi$identifier,
    version = version$name,
    tenancy = dataset$tenancy,
    created_at = dataset$created_at,
    data = data
  )
}

human_size <- function(size) {
  units <- c("B", "KB", "MB", "GB", "TB")
  value <- as.numeric(size)
  i <- 1
  while (value >= 1024 && i < length(units)) {
    value <- value / 1024
    i <- i + 1
  }
  if (i == 1) sprintf("%d B", as.integer(value)) else sprintf("%.1f %s", value, units[i])
}

#' @export
print.datamap_dataset <- function(x, ...) {
  cat(sprintf("<Dataset %s v%s · %d files · %s>\n", x$id, x$version_name, nrow(x$files), human_size(sum(x$files$size_bytes))))
  if (nrow(x$files) > 0) {
    width <- max(nchar(x$files$name))
    for (i in seq_len(nrow(x$files))) {
      note <- if (x$files$local[i]) "" else "   not mounted"
      cat(sprintf("  %-*s  %9s  %s%s\n", width, x$files$name[i], human_size(x$files$size_bytes[i]), ifelse(is.na(x$files$type[i]), "", x$files$type[i]), note))
    }
  }
  invisible(x)
}
```

Add `withr` to `Suggests` in `DESCRIPTION` (the tests use it).

Run: `cd r && Rscript -e 'devtools::test()'`
Expected: 5 passed. Then `R CMD build . && R CMD check datamap_0.1.0.tar.gz --no-manual` with no ERROR or WARNING (a NOTE about the non-standard `open` masking `base::open` is expected; the package exports `open` on purpose so the first cell reads `datamap::open()`; document it in `r/README.md`).

- [ ] **Step 4: Commit**

```bash
git add r
git commit -m "feat(r): datamap::open() with the files' local paths and a readable print

The package has no conveniences: ncdf4, readr and data.table already take a
path, and path() is the whole bridge."
```

---

### Task 6: CI and releases

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: CI**

`.github/workflows/ci.yml`:

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  python:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: python
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: python -m pytest -q

  r:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: r
    steps:
      - uses: actions/checkout@v4
      - uses: r-lib/actions/setup-r@v2
        with:
          r-version: "4.4"
          use-public-rspm: true
      - uses: r-lib/actions/setup-r-dependencies@v2
        with:
          working-directory: r
          extra-packages: any::rcmdcheck, any::devtools, any::withr
      - uses: r-lib/actions/check-r-package@v2
        with:
          working-directory: r
          args: 'c("--no-manual", "--as-cran")'
          error-on: '"warning"'
```

- [ ] **Step 2: Releases**

`.github/workflows/release.yml`:

```yaml
name: release

# v* publishes the Python package to PyPI (trusted publishing: register the
# repository as a publisher for the `datamap` project on pypi.org first).
# r-* creates a GitHub release the notebook image installs the R package from.
on:
  push:
    tags: ["v*", "r-*"]

jobs:
  pypi:
    if: startsWith(github.ref_name, 'v')
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    defaults:
      run:
        working-directory: python
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: python/dist

  r-release:
    if: startsWith(github.ref_name, 'r-')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: r-lib/actions/setup-r@v2
        with:
          r-version: "4.4"
      - run: cd r && R CMD build . --no-manual
      - uses: softprops/action-gh-release@v2
        with:
          files: r/datamap_*.tar.gz
```

The notebook image (plan 02) installs with `remotes::install_github('ardc-brazil/datamap-sdk', ref='r-0.1.0', subdir='r')`, which reads the tag, so the release asset is a convenience, not a dependency.

- [ ] **Step 3: Push, tag, verify**

```bash
gh repo create ardc-brazil/datamap-sdk --public --source . --push
git tag v0.1.0 && git tag r-0.1.0
git push origin v0.1.0 r-0.1.0
```

Expected: CI green on `main`; the `release` workflow publishes `datamap 0.1.0` to PyPI (after the trusted publisher is registered) and creates the `r-0.1.0` release. Verify: `pip download datamap==0.1.0 --no-deps -d /tmp/x` fetches a wheel, and `Rscript -e "remotes::install_github('ardc-brazil/datamap-sdk', ref='r-0.1.0', subdir='r'); library(datamap)"` loads.

---

### Task 7: Prove it in a session

- [ ] **Step 1: Against the smoke stack**

With plan 02's image rebuilt against these releases (`--build-arg DATAMAP_SDK_VERSION=0.1.0 --build-arg DATAMAP_R_SDK_REF=r-0.1.0`) and its smoke stack up:

```bash
docker exec datamap-notebook-0f3a4c7e-1b2d-4e5f-8a9b-0c1d2e3f4a5b python -c "
import datamap
ds = datamap.open()
print(ds.files)
print(ds.path('sample.nc'))
"
docker exec datamap-notebook-0f3a4c7e-1b2d-4e5f-8a9b-0c1d2e3f4a5b Rscript -e "
library(datamap); ds <- datamap::open(); print(ds); cat(ds\$path('sample.nc'))"
```

Expected: both print `<Dataset 9e8d7c6b-... v1 · 1 files · 64 B>`, the file line, and `/data/9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b/1/sample.nc`. The smoke stack's stub answers the manifest only; for `open()` it needs the two dataset routes stubbed too — add `datasets.json` to `infrastructure/jupyterhub/smoke/wiremock/mappings/` (gatekeeper repo) with `GET /api/v1/datasets/<DATASET_ID>` and `GET /api/v1/datasets/<DATASET_ID>/versions/1` returning the shapes `tests/test_dataset.py` uses, and extend plan 02's `test_both_kernels_and_both_sdks_are_present` to run the two commands above.

- [ ] **Step 2: Against the real thing**

Once plan 01 and plan 02 are deployed, open a notebook from the webapp (plan 05) or start a session through the API, and run the first cell. `ds.files` prints the selection with every file `local`; `ds.open_mfdataset()` opens the NetCDF files; `datamap.open("<another id>", version="1")` lists a dataset the user can read and raises `DataMapError(404)` for one they cannot.
