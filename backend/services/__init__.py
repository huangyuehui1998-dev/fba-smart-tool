"""编排层:包装 fba_tool 纯逻辑 + 路由间共享的业务胶水。

约定:本层只向下依赖 fba_tool / utils / schemas,不依赖 routers。
"""
