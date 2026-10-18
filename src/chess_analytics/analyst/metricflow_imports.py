# pyright: reportMissingImports=false
"""Return MetricFlow symbols. The package is installed only with the dbt extra.

These imports stay unresolved in the default type-check. Callers see the real
classes when the extra is installed, so signature errors are still reported.
"""


def query_request():
    from metricflow.engine.metricflow_engine import MetricFlowQueryRequest

    return MetricFlowQueryRequest


def metricflow_engine():
    from metricflow.engine.metricflow_engine import MetricFlowEngine

    return MetricFlowEngine


def parse_dbt_manifest():
    from metricflow_semantics.model.dbt_manifest_parser import (
        parse_manifest_from_dbt_generated_manifest,
    )

    return parse_manifest_from_dbt_generated_manifest


def manifest_lookup():
    from metricflow_semantics.model.semantic_manifest_lookup import SemanticManifestLookup

    return SemanticManifestLookup


def sql_engine():
    from metricflow.protocols.sql_client import SqlEngine

    return SqlEngine


def duckdb_renderer():
    from metricflow.sql.render.duckdb_renderer import DuckDbSqlPlanRenderer

    return DuckDbSqlPlanRenderer


def manifest_validator():
    from metricflow_semantic_interfaces.validations.semantic_manifest_validator import (
        SemanticManifestValidator,
    )

    return SemanticManifestValidator
