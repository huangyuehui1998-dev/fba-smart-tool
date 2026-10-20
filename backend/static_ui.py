"""前端静态资源路径（兼容旧引用；挂载逻辑已移至 main.py）。"""

from __future__ import annotations



import os

import sys



from main import _frontend_dist_dir, _mount_frontend_spa



__all__ = ["resolve_frontend_dist", "mount_frontend_spa"]





def resolve_frontend_dist() -> str | None:

    dist = _frontend_dist_dir()

    if os.path.isfile(os.path.join(dist, "index.html")) or os.path.isfile(

        os.path.join(dist, "_shell.html")

    ):

        return dist

    return None





def mount_frontend_spa(app) -> bool:

    _mount_frontend_spa(app)

    return resolve_frontend_dist() is not None

