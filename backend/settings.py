"""全局常量与跨路由共享配置。



仅存放"魔法值"与静态配置常量；业务可调参数仍在 fba_tool/user_config.py。

"""

from __future__ import annotations



# CORS —— 本地开发前端来源白名单

CORS_ALLOW_ORIGINS = [

    "http://127.0.0.1:5173",

    "http://localhost:5173",

    "http://127.0.0.1:5174",

    "http://localhost:5174",

    "http://127.0.0.1:5175",

    "http://localhost:5175",

]

CORS_ALLOW_ORIGIN_REGEX = r"https?://(127\.0\.0\.1|localhost)(:\d+)?"



# 导出文件 MIME 类型

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"



# ── FBA 物理红线（与 fba_tool.fba_compliance 一致，集中导出供跨模块引用）──

from fba_tool.fba_compliance import (  # noqa: E402

    FBA_MAX_SIDE_CM,

    FBA_MAX_SIDE_IN,

    FBA_MAX_STANDARD_GROSS_KG,

    FBA_MAX_STANDARD_GROSS_LB,

)



# ── 默认业务参数（与 user_config.DEFAULT_SETTINGS.parameters 对齐）──

DEFAULT_THROW_RATIO = 6000

DEFAULT_VOLUME_DIVISOR = 6000

DEFAULT_WEIGHT_LIMIT_KG = 22.5

DEFAULT_MAX_MIXED_ITEMS_PER_BOX = 40



# 单位换算（与 user_settings 默认值一致）

KG_TO_LB_FACTOR = 2.20462

LB_TO_KG_FACTOR = 0.453592

CM_TO_INCH_FACTOR = 0.393701

INCH_TO_CM_FACTOR = 2.54



# 发票模板进程内缓存

INVOICE_TEMPLATE_CACHE_MAX_ENTRIES = 12

