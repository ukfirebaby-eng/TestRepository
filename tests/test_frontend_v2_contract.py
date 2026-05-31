import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_frontend_v2_project_contract_exists():
    package_path = FRONTEND / "package.json"
    package_json = json.loads(package_path.read_text(encoding="utf-8"))

    assert package_json["scripts"]["dev"]
    assert package_json["scripts"]["build"]
    assert package_json["scripts"]["test"]
    assert package_json["scripts"]["typecheck"]
    assert package_json["scripts"]["e2e"]
    assert package_json["scripts"]["e2e:headed"]
    assert package_json["dependencies"]["@vitejs/plugin-react"]
    assert package_json["dependencies"]["@react-three/fiber"]
    assert package_json["dependencies"]["sigma"]
    assert package_json["dependencies"]["graphology"]
    assert package_json["dependencies"]["three"]
    assert package_json["devDependencies"]["@playwright/test"]


def test_frontend_v2_source_boundaries_exist():
    expected_paths = [
        "src/api/client.ts",
        "src/graph/normalize.ts",
        "src/graph/lenses.ts",
        "src/components/SpatialCanvas3D.tsx",
        "src/components/AnalystMap2D.tsx",
        "src/components/CommandCenterApp.tsx",
    ]

    missing = [path for path in expected_paths if not (FRONTEND / path).exists()]
    assert missing == []


def test_frontend_v2_build_targets_static_app_v2():
    vite_config = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")

    assert "outDir" in vite_config
    assert "../static/app-v2" in vite_config
    assert "proxy" in vite_config
    assert "http://localhost:8000" in vite_config


def test_frontend_v2_e2e_foundation_exists():
    playwright_config = FRONTEND / "playwright.config.ts"
    e2e_smoke = FRONTEND / "e2e" / "app-v2.spec.ts"

    assert playwright_config.exists()
    assert e2e_smoke.exists()

    config = playwright_config.read_text(encoding="utf-8")
    smoke = e2e_smoke.read_text(encoding="utf-8")

    assert "testDir" in config
    assert "./e2e" in config
    assert "baseURL" in config
    assert "/app-v2" in smoke
    assert "Analyst Map" in smoke
