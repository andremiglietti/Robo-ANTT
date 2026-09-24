"""
Testes de checkpoint.py - achado na revisão crítica de 24/09/2026: era o
único módulo central do robô sem NENHUM teste dedicado, apesar de guardar
o estado mais importante entre execuções (autos processados, falhas
pendentes, garantia de varredura completa).
"""
import json

import pytest

from robo_antt import checkpoint


def test_carregar_arquivo_inexistente_devolve_estado_vazio(tmp_path):
    estado = checkpoint.carregar(tmp_path / "nao_existe.json")
    assert estado["processados"] == set()
    assert estado["falhas"] == {}
    assert estado["varreduras_completas"] == []
    assert estado["ultima_execucao"] is None


def test_marcar_processado_e_ja_processado(tmp_path):
    estado = checkpoint.carregar(tmp_path / "checkpoint.json")
    assert not checkpoint.ja_processado(estado, "AUTO123")
    checkpoint.marcar_processado(estado, "AUTO123")
    assert checkpoint.ja_processado(estado, "AUTO123")


def test_marcar_processado_remove_falha_pendente_do_mesmo_auto(tmp_path):
    estado = checkpoint.carregar(tmp_path / "checkpoint.json")
    checkpoint.marcar_falha(estado, "AUTO123", "erro qualquer", cnpj="123", tipo_value="2")
    assert "AUTO123" in estado["falhas"]
    checkpoint.marcar_processado(estado, "AUTO123")
    assert "AUTO123" not in estado["falhas"]


def test_salvar_e_carregar_faz_round_trip_com_processados_como_set(tmp_path):
    """`processados` vira `set` em memória (fix de 24/09/2026 - antes era
    uma `list`, com `ja_processado()` fazendo scan O(n) a cada chamada,
    igual ao bug já corrigido em planilha.ja_registrado() em 22/09/2026).
    O JSON em disco continua sendo uma lista (ordenada, legível/diffável) -
    só a representação em memória mudou."""
    caminho = tmp_path / "checkpoint.json"
    estado = checkpoint.carregar(caminho)
    checkpoint.marcar_processado(estado, "AUTO_B")
    checkpoint.marcar_processado(estado, "AUTO_A")
    checkpoint.marcar_processado(estado, "AUTO_B")  # duplicado de propósito - não pode duplicar no set
    checkpoint.salvar(estado, caminho)

    # no disco, é uma lista ordenada (não um objeto set, que json não sabe serializar)
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    assert bruto["processados"] == ["AUTO_A", "AUTO_B"]

    # recarregado, volta a ser um set utilizável por ja_processado()
    recarregado = checkpoint.carregar(caminho)
    assert recarregado["processados"] == {"AUTO_A", "AUTO_B"}
    assert checkpoint.ja_processado(recarregado, "AUTO_A")


def test_falhas_retentaveis_so_inclui_falhas_com_cnpj_e_tipo(tmp_path):
    estado = checkpoint.carregar(tmp_path / "checkpoint.json")
    checkpoint.marcar_falha(estado, "COM_INFO", "erro", cnpj="92660604000182", tipo_value="2")
    checkpoint.marcar_falha(estado, "SEM_INFO", "erro legado")  # cnpj/tipo_value default None

    retentaveis = checkpoint.falhas_retentaveis(estado)
    autos = [r[0] for r in retentaveis]
    assert "COM_INFO" in autos
    assert "SEM_INFO" not in autos
    assert retentaveis == [("COM_INFO", "92660604000182", "2")]


def test_migracao_de_falha_legada_formato_string_vira_dict(tmp_path):
    """Checkpoints salvos antes de 19/09/2026 guardavam `falhas` como
    {auto: "motivo"} (string simples) - carregar() precisa migrar isso pro
    formato novo {auto: {"motivo", "cnpj", "tipo_value"}} sem quebrar."""
    caminho = tmp_path / "checkpoint.json"
    caminho.write_text(
        json.dumps({"processados": ["X"], "falhas": {"Y": "motivo antigo em texto puro"}}),
        encoding="utf-8",
    )
    estado = checkpoint.carregar(caminho)
    assert estado["falhas"]["Y"] == {"motivo": "motivo antigo em texto puro", "cnpj": None, "tipo_value": None}
    assert checkpoint.falhas_retentaveis(estado) == []  # sem cnpj/tipo, não é retentável direto


def test_checkpoint_de_antes_de_17_09_sem_varreduras_completas_nao_quebra(tmp_path):
    caminho = tmp_path / "checkpoint.json"
    caminho.write_text(json.dumps({"processados": [], "falhas": {}}), encoding="utf-8")
    estado = checkpoint.carregar(caminho)
    assert estado["varreduras_completas"] == []


def test_marcar_varredura_completa_nao_duplica(tmp_path):
    estado = checkpoint.carregar(tmp_path / "checkpoint.json")
    checkpoint.marcar_varredura_completa(estado, "92660604000182", "2")
    checkpoint.marcar_varredura_completa(estado, "92660604000182", "2")
    assert estado["varreduras_completas"] == ["92660604000182|2"]


def test_json_corrompido_levanta_erro_claro_em_vez_de_json_decode_error_cru(tmp_path):
    """Achado na revisão crítica de 24/09/2026: carregar() não tinha
    NENHUM tratamento pra JSON corrompido - um checkpoint truncado
    derrubava a execução inteira com um json.JSONDecodeError cru, sem a
    mesma cortesia de relatório limpo que o resto do projeto garante."""
    caminho = tmp_path / "checkpoint.json"
    caminho.write_text("{ isso não é um json válido", encoding="utf-8")

    with pytest.raises(checkpoint.CheckpointCorrompidoError):
        checkpoint.carregar(caminho)


def test_salvar_preserva_falhas_e_varreduras_completas(tmp_path):
    caminho = tmp_path / "checkpoint.json"
    estado = checkpoint.carregar(caminho)
    checkpoint.marcar_falha(estado, "AUTO1", "erro", cnpj="123", tipo_value="2")
    checkpoint.marcar_varredura_completa(estado, "123", "2")
    checkpoint.salvar(estado, caminho)

    recarregado = checkpoint.carregar(caminho)
    assert recarregado["falhas"]["AUTO1"]["motivo"] == "erro"
    assert recarregado["varreduras_completas"] == ["123|2"]
    assert recarregado["ultima_execucao"] is not None
