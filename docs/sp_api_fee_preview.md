# Fee Preview 报告类型（PR-5 核实）

核实来源：Amazon Selling Partner API，Report Type Values → Fulfillment by Amazon (FBA) Reports。  
页面：<https://developer-docs.amazon/sp-api/docs/report-type-values-fba>  
核实日：2026-10-20。

## 报告类型

| 项 | 值 |
|---|---|
| 卖家后台名称 | FBA Fee Preview Report |
| `reportType` | `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` |
| 接口 | Reports API `createReport`（本轮不调用） |
| 文件 | 制表符分隔的文本 |

官方说明：内容至少每 72 小时更新一次。生成报告时 `dataStartTime` 至少要早于当前时间 72 小时，`dataEndTime` 为当前时间。

## 本轮用到的列

商品级对比只读上传的报告文件，不请求 SP-API。

- `sku`
- `asin`
- `longest-side` / `median-side` / `shortest-side`
- `unit-of-dimension`（inches 或 centimeters）
- `item-package-weight`
- `unit-of-weight`（pounds 或 kilograms）
- `product-size-tier`（美国站尺寸分段；欧盟站对应 `product-size-weight-band`）
- `currency`
- `amazon-store`（站点；缺省时由文件名或导入参数指定）

缺少 `item-package-weight`（或同义的 weight 列）时整份文件拒绝，返回 422，不写库。

## 不在本轮调用的原因

报告类型已经对上官方 Report Type Values。在 Marco 提供一份真实样本、并且接入授权之前，商品级只支持上传该报告的 txt/tsv 文件。不设亚马逊箱级实测适配器：`listShipmentBoxes` 返回的是卖家自己提交的值，不是过机实测。
