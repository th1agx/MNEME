import sys

import pytest

from mneme import openmp


def test_fora_do_mac_nao_faz_nada():
    assert openmp.preparar("linux") is None


@pytest.mark.skipif(sys.platform != "darwin", reason="só no macOS")
def test_lightgbm_e_xgboost_carregam_no_mac():
    import lightgbm
    import xgboost

    assert lightgbm.__version__ and xgboost.__version__
