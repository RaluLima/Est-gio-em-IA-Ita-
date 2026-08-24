"""Contratos de dados compartilhados entre agente, lote e confronto."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ParecerLLM(BaseModel):
    """Contrato de saída obrigatório do parecer do agente."""

    nivel_risco: Literal["baixo", "médio", "alto"]
    tipologia_suspeita: str = Field(min_length=3)
    red_flags: list[str] = Field(min_length=1)
    justificativa: str = Field(min_length=10)

    @field_validator("nivel_risco", mode="before")
    @classmethod
    def _normalizar(cls, v):
        v = str(v).strip().lower()
        return {"medio": "médio"}.get(v, v)


class DecisaoFerramenta(BaseModel):
    """Decisão do agente de chamar uma ferramenta."""

    acao: Literal["ferramenta"]
    ferramenta: str
    argumentos: dict = Field(default_factory=dict)


class DecisaoFinal(BaseModel):
    """Decisão do agente de encerrar com parecer."""

    acao: Literal["parecer_final"]
    nivel_risco: str
    tipologia_suspeita: str
    red_flags: list[str]
    justificativa: str
