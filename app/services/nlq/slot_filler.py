# -*- coding: utf-8 -*-
"""
NLQ Kademe 1 - Slot Doldurma

TopNIntent (ham metin ipuclari) + sema metadata (table_profiles,
datasets_relationships) -> somut tablo/kolon/join eslestirmesi.

table_profiles beklenen format (granularity_analyzer.py / /api/analyze
{conn_id}/results ile TEYIT EDILMELI):
  [{"schema": "Production", "table": "Product",
    "columns": {"Name": "categorical", "ListPrice": "metric", ...}}, ...]

relationships beklenen format:
  [{"table_a": "Sales.SalesOrderDetail", "column_a": "ProductID",
    "table_b": "Production.Product", "column_b": "ProductID"}, ...]
"""
from rapidfuzz import fuzz, process

from .synonyms import expand_dimension_hint, expand_metric_hint

MIN_SCORE = 60
MAX_JOIN_HOPS = 3


class FilledSlots:
    __slots__ = (
        "dimension_table", "dimension_schema", "dimension_display_col",
        "metric_table", "metric_schema", "metric_col",
        "join_path", "confidence",
    )

    def __init__(self, dimension_table, dimension_schema, dimension_display_col,
                 metric_table, metric_schema, metric_col, join_path, confidence):
        self.dimension_table = dimension_table
        self.dimension_schema = dimension_schema
        self.dimension_display_col = dimension_display_col
        self.metric_table = metric_table
        self.metric_schema = metric_schema
        self.metric_col = metric_col
        self.join_path = join_path
        self.confidence = confidence

    def __repr__(self):
        return (f"FilledSlots(dim={self.dimension_schema}.{self.dimension_table}."
                f"{self.dimension_display_col}, metric={self.metric_schema}.{self.metric_table}."
                f"{self.metric_col}, join={self.join_path}, conf={self.confidence:.1f})")


def _match_dimension_table(dimension_hint, table_profiles):
    candidates = expand_dimension_hint(dimension_hint)
    table_names = [tp["table"] for tp in table_profiles]

    best_table = None
    best_score = 0
    for cand in candidates:
        match = process.extractOne(cand, table_names, scorer=fuzz.WRatio)
        if match and match[1] > best_score:
            best_table, best_score = match[0], match[1]

    if best_table is None or best_score < MIN_SCORE:
        return None, 0

    tp = next(tp for tp in table_profiles if tp["table"] == best_table)
    return tp, best_score


def _display_column(table_profile):
    for col, cls in table_profile["columns"].items():
        if cls == "categorical":
            return col
    for col, cls in table_profile["columns"].items():
        if cls == "identifier":
            return col
    return list(table_profile["columns"].keys())[0]


def _match_metric_column(metric_hint, table_profiles):
    candidates = expand_metric_hint(metric_hint)

    best = None
    for tp in table_profiles:
        metric_cols = [c for c, cls in tp["columns"].items() if cls == "metric"]
        if not metric_cols:
            continue
        for cand in candidates:
            match = process.extractOne(cand, metric_cols, scorer=fuzz.WRatio)
            if match and (best is None or match[1] > best[2]):
                best = (tp, match[0], match[1])

    if best is None or best[2] < MIN_SCORE:
        return None, None, 0
    return best[0], best[1], best[2]


def _find_join_path(from_table_key, to_table_key, relationships, max_hops=MAX_JOIN_HOPS):
    """BFS ile iki tablo arasi en kisa join yolunu bulur (max_hops sinirli)."""
    if from_table_key == to_table_key:
        return []

    adjacency = {}
    for rel in relationships:
        a, b = rel["table_a"], rel["table_b"]
        adjacency.setdefault(a, []).append((b, rel["column_a"], rel["column_b"]))
        adjacency.setdefault(b, []).append((a, rel["column_b"], rel["column_a"]))

    from collections import deque
    visited = {from_table_key}
    queue = deque([(from_table_key, [])])

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for neighbor, col_here, col_there in adjacency.get(current, []):
            if neighbor in visited:
                continue
            new_path = path + [{"table": neighbor, "on_a": col_here, "on_b": col_there}]
            if neighbor == to_table_key:
                return new_path
            visited.add(neighbor)
            queue.append((neighbor, new_path))

    return None


def fill_slots(intent, table_profiles, relationships):
    """TopNIntent -> FilledSlots (veya None eger yeterli guvenle eslesme yoksa)"""
    dim_tp, dim_score = _match_dimension_table(intent.dimension_hint, table_profiles)
    if dim_tp is None:
        return None

    metric_tp, metric_col, metric_score = _match_metric_column(intent.metric_hint, table_profiles)
    if metric_tp is None:
        return None

    dim_key = f"{dim_tp['schema']}.{dim_tp['table']}"
    metric_key = f"{metric_tp['schema']}.{metric_tp['table']}"

    join_path = None
    if dim_key != metric_key:
        join_path = _find_join_path(dim_key, metric_key, relationships)
        if join_path is None:
            return None

    display_col = _display_column(dim_tp)
    overall_confidence = min(dim_score, metric_score)

    return FilledSlots(
        dimension_table=dim_tp["table"],
        dimension_schema=dim_tp["schema"],
        dimension_display_col=display_col,
        metric_table=metric_tp["table"],
        metric_schema=metric_tp["schema"],
        metric_col=metric_col,
        join_path=join_path,
        confidence=overall_confidence,
    )
