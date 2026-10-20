"""跑测试时 app_data 必须在临时目录，不能是项目里的真实 app_data。"""
from fba_tool.app_paths import app_data_dir, master_db_path, project_root


def test_app_data_is_isolated():
    real = (project_root() / "app_data").resolve()
    assert app_data_dir().resolve() != real
    assert real not in master_db_path().resolve().parents
