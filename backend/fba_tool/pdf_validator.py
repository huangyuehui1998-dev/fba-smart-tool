from __future__ import annotations



import io

import re

from typing import List, Tuple



import pandas as pd

import pdfplumber



from fba_tool.shipment_parser import parse_pdf_shipment

from fba_tool.shipment_validator import cross_validate_box_data



WAREHOUSE_CODE_RE = re.compile(r"\b([A-Z]{3,4}\d)\b")





def extract_warehouse_from_pdf(file_bytes: bytes) -> str:

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:

        if not pdf.pages:

            return ""

        text = pdf.pages[0].extract_text() or ""

    for token in text.replace("\n", " ").split():

        m = WAREHOUSE_CODE_RE.match(token.strip())

        if m:

            code = m.group(1)

            if code.startswith("FBA"):

                continue

            return code

    return ""





def parse_box_label_pdf(file_bytes: bytes) -> pd.DataFrame:

    return parse_pdf_shipment(file_bytes).box_items





def extract_shipment_id_from_pdf(file_bytes: bytes) -> str:

    return parse_pdf_shipment(file_bytes).shipment_id


