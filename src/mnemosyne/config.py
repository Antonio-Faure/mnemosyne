"""Configuration loading: YAML file + environment overrides."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# Repository root = .../mnemosyne (config.py lives in src/mnemosyne/)
ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseModel):
    data_dir: str = "data"
    vault_path: str = "vault/vault.enc"
    journal_dir: str = "journal"
    control_dir: str = "control"
    log_level: str = "INFO"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class HeartbeatConfig(BaseModel):
    tick_seconds: int = 15
    max_workers: int = 4
    job_timeout_s: int = 300
    stale_lock_s: int = 600


class WarmupPhase(BaseModel):
    until_day: int | None = None
    outbound_per_day: int = 0
    harvest_per_day: int = 200


class ReputationConfig(BaseModel):
    #: ISO date the agent's account was created; null => warmup disabled (trusted).
    account_created_at: str | None = None
    domain_min_interval_s: float = 1.0
    block_cooldown_s: int = 300
    warmup: list[WarmupPhase] = Field(
        default_factory=lambda: [
            WarmupPhase(until_day=3, outbound_per_day=0, harvest_per_day=50),
            WarmupPhase(until_day=10, outbound_per_day=3, harvest_per_day=150),
            WarmupPhase(until_day=None, outbound_per_day=20, harvest_per_day=1000),
        ]
    )


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str | None = None
    model: str | None = None
    #: key used inside the opencode auth store (e.g. "opencode-go")
    auth_provider: str | None = None


class LlmConfig(BaseModel):
    default: str = "zen"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class IdentityConfig(BaseModel):
    """Public identity disclosed in every email / contact form (transparency)."""

    name: str = "mnemosyne"
    purpose: str = (
        "a free and open research project that aggregates public historical "
        "image archives so they are easier to find and reuse"
    )
    repo_url: str = "https://github.com/Antonio-Faure/mnemosyne"
    agent_email: str | None = None
    language: str = "fr"


class AgentsConfig(BaseModel):
    """Stirrup agent loop settings (browser onboarding / outreach)."""

    max_turns: int = 40
    #: per-turn generation budget required by the Stirrup chat client.
    max_tokens: int = 8192
    context_window_tokens: int = 128000
    output_dir: str = "data/agent-runs"


class MemoryConfig(BaseModel):
    """Bounds the LLM context (and therefore the cost) of long-running agents."""

    #: how many of the most recent messages are always sent verbatim
    max_recent_messages: int = 12
    #: compact once the stored history exceeds this many messages
    compact_after_messages: int = 24
    #: a rolling summary is kept per session; instruct the model to stay concise
    summary_instruction: str = (
        "Résume la conversation ci-dessus en puces factuelles et durables "
        "(décisions, faits, accès obtenus, tâches en cours, échecs). "
        "Conserve les identifiants, URLs et clés de données (jamais les secrets). "
        "Sois concis : au plus 200 mots."
    )


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token_env: str = "MNEMOSYNE_TELEGRAM_BOT_TOKEN"
    chat_id_env: str = "MNEMOSYNE_TELEGRAM_CHAT_ID"


class NotifyConfig(BaseModel):
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    reputation: ReputationConfig = Field(default_factory=ReputationConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    sources_dir: str = "config/sources"

    #: absolute path to the repository root, set by the loader
    root: Path = ROOT

    @property
    def data_path(self) -> Path:
        return (self.root / self.app.data_dir).resolve()

    @property
    def vault_file(self) -> Path:
        return (self.root / self.app.vault_path).resolve()

    @property
    def journal_path(self) -> Path:
        return (self.root / self.app.journal_dir).resolve()

    @property
    def control_path(self) -> Path:
        return (self.root / self.app.control_dir).resolve()

    @property
    def sources_path(self) -> Path:
        return (self.root / self.sources_dir).resolve()

    def db_file(self) -> Path:
        return self.data_path / "mnemosyne.db"


def load_config(config_path: str | Path | None = None) -> Config:
    path = Path(
        config_path
        or os.environ.get("MNEMOSYNE_CONFIG", "")
        or (ROOT / "config" / "config.yaml")
    )
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = Config(**raw)
    cfg.root = ROOT

    # Environment overrides (paths / log level).
    if os.environ.get("MNEMOSYNE_DATA_DIR"):
        cfg.app.data_dir = os.environ["MNEMOSYNE_DATA_DIR"]
    if os.environ.get("MNEMOSYNE_VAULT_PATH"):
        cfg.app.vault_path = os.environ["MNEMOSYNE_VAULT_PATH"]
    if os.environ.get("MNEMOSYNE_LOG_LEVEL"):
        cfg.app.log_level = os.environ["MNEMOSYNE_LOG_LEVEL"]
    return cfg


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()
