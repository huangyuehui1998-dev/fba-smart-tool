from pathlib import Path

from fba_tool.fnsku_resolve import build_fnsku_map, resolve_fnsku
from fba_tool.product_catalog import ProductCatalog, ProductRecord


class _Catalog:
    def __init__(self, mapping):
        self.mapping = mapping

    def lookup(self, sku: str):
        rec = self.mapping.get(sku)
        if rec is None:
            return None
        return type("Rec", (), rec)()


def test_csv_beats_all_other_sources():
    catalog = _Catalog({"SKU-A": {"fnsku": "X0CATALOG"}})
    fnsku = resolve_fnsku(
        "SKU-A",
        csv_fnsku="X0FROMCSV",
        step1_fnsku="X0STEP1",
        catalog=catalog,
        json_map={"SKU-A": "X0JSON"},
        master_map={"SKU-A": "X0MASTER"},
    )
    assert fnsku == "X0FROMCSV"


def test_step1_beats_master_and_catalog():
    catalog = _Catalog({"SKU-A": {"fnsku": "X0CATALOG"}})
    fnsku = resolve_fnsku(
        "SKU-A",
        csv_fnsku="",
        step1_fnsku="X0STEP1",
        catalog=catalog,
        json_map={"SKU-A": "X0JSON"},
        master_map={"SKU-A": "X0MASTER"},
    )
    assert fnsku == "X0STEP1"


def test_master_beats_catalog_and_json():
    catalog = _Catalog({"SKU-A": {"fnsku": "X0CATALOG"}})
    fnsku = resolve_fnsku(
        "SKU-A",
        catalog=catalog,
        json_map={"SKU-A": "X0JSON"},
        master_map={"SKU-A": "X0MASTER"},
    )
    assert fnsku == "X0MASTER"


def test_catalog_beats_json():
    catalog = _Catalog({"SKU-A": {"fnsku": "X0CATALOG"}})
    fnsku = resolve_fnsku(
        "SKU-A",
        catalog=catalog,
        json_map={"SKU-A": "X0JSON"},
        master_map={},
    )
    assert fnsku == "X0CATALOG"


def test_json_fallback():
    fnsku = resolve_fnsku(
        "SKU-A",
        catalog=_Catalog({}),
        json_map={"SKU-A": "X0JSON"},
        master_map={},
    )
    assert fnsku == "X0JSON"


def test_empty_when_unknown():
    fnsku = resolve_fnsku("SKU-UNKNOWN", catalog=_Catalog({}), json_map={}, master_map={})
    assert fnsku == ""


def _catalog(**records: str) -> ProductCatalog:
    return ProductCatalog(
        source_path=Path("test.csv"),
        records={sku: ProductRecord(sku=sku, fnsku=fnsku) for sku, fnsku in records.items()},
    )


def test_catalog_substring_match_requires_unique_candidate():
    """PETBED-M 同时是 PETBED-MAT 和 PETBED-MINI 的子串 → 拒绝而非任选其一。"""
    cat = _catalog(**{"PETBED-MAT": "X0MAT00000", "PETBED-MINI": "X0MINI00000"})
    assert cat.lookup_with_match("PETBED-M") == (None, "ambiguous")
    assert cat.lookup("PETBED-M") is None

    only_one = _catalog(**{"PETBED-MAT": "X0MAT00000"})
    rec, kind = only_one.lookup_with_match("PETBED-M")
    assert kind == "fuzzy" and rec.fnsku == "X0MAT00000"

    exact = _catalog(**{"PETBED-MAT": "X0MAT00000"})
    assert exact.lookup_with_match("PETBED-MAT")[1] == "exact"


def test_ambiguous_catalog_does_not_leak_into_fnsku():
    cat = _catalog(**{"PETBED-MAT": "X0MAT00000", "PETBED-MINI": "X0MINI00000"})
    assert resolve_fnsku("PETBED-M", catalog=cat, json_map={}, master_map={}) == ""


def test_build_fnsku_map_matches_resolve_fnsku_priority():
    """Step 3 批量解析必须与 Step 4 单条解析给出同一结果，否则 STA 与贴标单会分叉。"""
    cat = _catalog(**{"SKU-C": "X0CATALOG0"})
    args = dict(catalog=cat, json_map={"SKU-B": "X0JSON0000"}, master_map={"SKU-A": "X0MASTER00"})

    built = build_fnsku_map(
        ["SKU-A", "SKU-B", "SKU-C", "SKU-D", ""],
        step1_map={"SKU-D": "X0STEP10000"},
        **args,
    )
    for sku in ("SKU-A", "SKU-B", "SKU-C", "SKU-D"):
        assert built.get(sku, "") == resolve_fnsku(
            sku, step1_fnsku={"SKU-D": "X0STEP10000"}.get(sku, ""), **args
        )
    assert built == {
        "SKU-A": "X0MASTER00",
        "SKU-B": "X0JSON0000",
        "SKU-C": "X0CATALOG0",
        "SKU-D": "X0STEP10000",
    }
