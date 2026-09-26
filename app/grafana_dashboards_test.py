import json
import re
import unittest
from pathlib import Path
from unittest.mock import Mock

from prometheus_client import CollectorRegistry

from app.metrics import Metrics
from app.platform_state import PlatformStateCollector

GRAFANA = Path(__file__).resolve().parent.parent / "infrastructure" / "grafana"
DASHBOARDS = GRAFANA / "dashboards"
EXTERNAL_METRICS = GRAFANA / "external-metrics.txt"

DATASOURCE_UIDS = {"prometheus", "loki", "grafana", "-- Grafana --"}

_METRIC = re.compile(r"\bdatamap_[a-z0-9_]+")
_SUFFIX = re.compile(r"_(total|bucket|sum|count|created)$")
_STRING = re.compile(r'"(?:\\.|[^"\\])*"|`[^`]*`')


def base_name(metric: str) -> str:
    return _SUFFIX.sub("", metric)


def dashboard_files() -> list[Path]:
    return sorted(DASHBOARDS.rglob("*.json"))


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def declared_metrics() -> set[str]:
    registry = Metrics(registry=CollectorRegistry()).registry
    repository = Mock()
    repository.datasets.return_value = []
    repository.files.return_value = (0, 0)
    repository.users.return_value = []
    repository.dois.return_value = []
    registry.register(PlatformStateCollector(repository))
    names = {base_name(family.name) for family in registry.collect()}
    for line in EXTERNAL_METRICS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(base_name(line))
    return names


def prometheus_queries(node, datasource_uid: str | None = None):
    if isinstance(node, list):
        for value in node:
            yield from prometheus_queries(value, datasource_uid)
        return
    if not isinstance(node, dict):
        return
    datasource = node.get("datasource")
    if isinstance(datasource, dict) and datasource.get("uid"):
        datasource_uid = datasource["uid"]
    if datasource_uid != "loki":
        for key in ("expr", "query", "definition"):
            if isinstance(node.get(key), str):
                yield node[key]
    for value in node.values():
        yield from prometheus_queries(value, datasource_uid)


def queried_metrics(dashboard: dict) -> set[str]:
    found = set()
    for query in prometheus_queries(dashboard):
        # Label values such as name=~"datamap_.*" are containers, not metrics.
        query = _STRING.sub('""', query)
        found |= {base_name(m) for m in _METRIC.findall(query)}
    return found


class TestDashboards(unittest.TestCase):
    def test_there_are_dashboards_to_check(self):
        self.assertTrue(dashboard_files(), f"no dashboards under {DASHBOARDS}")

    def test_every_dashboard_is_valid_json(self):
        for path in dashboard_files():
            with self.subTest(dashboard=path.name):
                json.loads(path.read_text())

    def test_uids_are_set_and_unique(self):
        seen = {}
        for path in dashboard_files():
            uid = json.loads(path.read_text()).get("uid")
            with self.subTest(dashboard=path.name):
                self.assertTrue(
                    uid, "a dashboard without a uid changes url on every load"
                )
                self.assertNotIn(uid, seen, f"uid also used by {seen.get(uid)}")
            seen[uid] = path.name

    def test_no_dashboard_carries_a_database_id(self):
        for path in dashboard_files():
            with self.subTest(dashboard=path.name):
                self.assertIsNone(json.loads(path.read_text()).get("id"))

    def test_only_the_provisioned_datasources_are_referenced(self):
        for path in dashboard_files():
            for node in walk(json.loads(path.read_text())):
                datasource = node.get("datasource")
                if not isinstance(datasource, dict):
                    continue
                with self.subTest(dashboard=path.name, datasource=datasource):
                    uid = datasource.get("uid", "")
                    self.assertTrue(
                        uid in DATASOURCE_UIDS or uid.startswith("$"),
                        "datasource uids are fixed in provisioning/datasources",
                    )

    def test_every_datamap_metric_queried_is_one_some_service_declares(self):
        declared = declared_metrics()
        for path in dashboard_files():
            missing = queried_metrics(json.loads(path.read_text())) - declared
            with self.subTest(dashboard=path.name):
                self.assertEqual(
                    missing,
                    set(),
                    "a panel on an undeclared metric draws nothing and looks quiet",
                )
