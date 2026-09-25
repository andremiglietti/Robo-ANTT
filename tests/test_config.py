"""
Testes de config.py - pasta de destino configurável por máquina/pessoa
(25/09/2026, ver CLAUDE.md: proposta feita pelo usuário pensando numa 2ª
pessoa usando o robô no computador dela, sem a mesma estrutura de
OneDrive/usuário do computador original).
"""
from pathlib import Path

from robo_antt import config


def test_carregar_sharepoint_dir_configurado_sem_arquivo_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", tmp_path / "nao_existe.json")
    assert config._carregar_sharepoint_dir_configurado() is None


def test_salvar_e_carregar_sharepoint_dir_faz_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", tmp_path / "config_local.json")
    pasta_escolhida = tmp_path / "Minha Pasta ANTT"

    config.salvar_sharepoint_dir(pasta_escolhida)

    assert config.CONFIG_LOCAL_PATH.exists()
    recarregado = config._carregar_sharepoint_dir_configurado()
    assert recarregado == pasta_escolhida


def test_carregar_sharepoint_dir_configurado_json_corrompido_devolve_none(tmp_path, monkeypatch):
    """Um config_local.json corrompido não pode derrubar a importação do
    módulo inteiro - trata como "nenhuma escolha salva ainda" (cai de
    volta no palpite padrão), não como erro fatal."""
    caminho = tmp_path / "config_local.json"
    caminho.write_text("{ isso não é json válido", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", caminho)
    assert config._carregar_sharepoint_dir_configurado() is None


def test_carregar_sharepoint_dir_configurado_sem_chave_devolve_none(tmp_path, monkeypatch):
    caminho = tmp_path / "config_local.json"
    caminho.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", caminho)
    assert config._carregar_sharepoint_dir_configurado() is None


def test_salvar_sharepoint_dir_cria_pasta_pai_se_necessario(tmp_path, monkeypatch):
    caminho = tmp_path / "subpasta_nova" / "config_local.json"
    monkeypatch.setattr(config, "CONFIG_LOCAL_PATH", caminho)
    config.salvar_sharepoint_dir(tmp_path / "Dados ANTT")
    assert caminho.exists()
