"""Validate shipment ID matching + true box index cross-check."""
from pathlib import Path

from fba_tool.excel_export import export_factory_sheet, export_forwarder_quote
from fba_tool.fba_parser import build_factory_df, build_forwarder_df
from fba_tool.shipment_validator import validate_shipments

tpl = Path("templates")
csv_files = sorted(tpl.glob("*.csv"))
pdf_files = sorted(tpl.glob("*.pdf"))

csv_payload = [(f.name, f.read_bytes()) for f in csv_files]
pdf_payload = [(f.name, f.read_bytes()) for f in pdf_files]

result = validate_shipments(csv_payload, pdf_payload)

print("\n=== AUTO MAPPING STATUS ===")
for line in result.status_lines:
    print(line.encode("ascii", "replace").decode("ascii"))

print("\n=== ERRORS ===")
for err in result.errors:
    print(err.encode("ascii", "replace").decode("ascii"))

print("\nALL PASS:", result.ok)

if result.ok:
    merged = build_factory_df(result.all_box_items)
    print("factory export bytes", len(export_factory_sheet(merged)))
    fwd = build_forwarder_df(result.all_box_specs)
    print("forwarder export bytes", len(export_forwarder_quote(fwd)))
