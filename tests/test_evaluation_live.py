from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.evaluation import evaluate_live_ingestion_fixture, live_evaluation_enabled


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"


def test_live_evaluation_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DIAMOND_MINER_LIVE_EVALUATION", raising=False)

    assert live_evaluation_enabled() is False


def test_live_evaluation_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("DIAMOND_MINER_LIVE_EVALUATION", "1")

    assert live_evaluation_enabled() is True


def test_live_ingestion_fixture_uses_real_orchestrator_path(tmp_path):
    vault = Mock()
    orchestrator = Mock()
    evaluation_result = {"passed": True}

    with patch("core.evaluation.HybridVault", return_value=vault) as vault_cls, \
         patch("core.evaluation.DiamondOrchestrator", return_value=orchestrator) as orchestrator_cls, \
         patch("core.evaluation.evaluate_baseline", return_value=evaluation_result) as evaluate:
        result = evaluate_live_ingestion_fixture(
            FIXTURE_DIR / "simple_programme_baseline.json",
            base_dir=tmp_path,
            tenant_id="live_eval_test",
            max_workers=1,
        )

    assert result == evaluation_result
    vault_cls.assert_called_once_with(tenant_id="live_eval_test", base_dir=str(tmp_path))
    orchestrator_cls.assert_called_once()
    orchestrator.run_ingestion_pipeline.assert_called_once()
    orchestrator.interrogate_friction.assert_called_once_with()
    orchestrator.interrogate_fragility.assert_called_once_with()
    orchestrator.interrogate_time_friction.assert_called_once_with()
    evaluate.assert_called_once()


pytestmark = pytest.mark.live_evaluation


@pytest.mark.skipif(not live_evaluation_enabled(), reason="Set DIAMOND_MINER_LIVE_EVALUATION=1 to run live model evaluation.")
def test_live_model_complex_programme_evaluation(tmp_path):
    result = evaluate_live_ingestion_fixture(
        FIXTURE_DIR / "complex_programme_live_baseline.json",
        base_dir=tmp_path,
        max_workers=1,
    )

    assert result["passed"] is True
