import io
import urllib.request

import pandas as pd

bio = io.BytesIO()
pd.DataFrame([["SKU", "产品名称"], ["UP-1", "EN"]]).to_excel(bio, index=False, header=False)
data = bio.getvalue()
boundary = "----BoundaryTest"
body = (
    ("--%s\r\n" % boundary)
    + 'Content-Disposition: form-data; name="file"; filename="t.xlsx"\r\n'
    + "Content-Type: application/octet-stream\r\n\r\n"
).encode("utf-8") + data + ("\r\n--%s--\r\n" % boundary).encode("utf-8")

for url in (
    "http://127.0.0.1:8011/api/master-data/upload/product-info",
    "http://127.0.0.1:5173/api/master-data/upload/product-info",
):
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(url, r.status, r.read().decode()[:200])
    except Exception as e:
        print(url, "ERR", e)
