"""Modelo validado dos critérios usados na busca de vagas."""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
import unicodedata


class CriteriaValidationError(ValueError):
    """Erro de validação dos critérios de busca."""


class WorkMode(str, Enum):
    """Modalidades de trabalho aceitas pelo modelo."""

    REMOTE = "remoto"
    ONSITE = "presencial"
    HYBRID = "híbrido"


def _normalize_text(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CriteriaValidationError(f"{name} deve ser um texto ou None.")
    normalized = value.strip()
    return normalized or None


def _normalize_salary(name: str, value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise CriteriaValidationError(f"{name} deve ser um valor numérico válido.")
    raw = str(value).strip()
    if raw.upper().startswith("R$"):
        raw = raw[2:].strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif len(raw.split(".")) > 1 and all(len(part) == 3 for part in raw.split(".")[1:]):
        raw = raw.replace(".", "")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise CriteriaValidationError(f"{name} deve ser um valor numérico válido.") from None
    if not amount.is_finite() or amount < 0:
        raise CriteriaValidationError(f"{name} deve ser finito e não negativo.")
    return amount


def _normalize_work_mode(value: WorkMode | str | None) -> WorkMode | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, WorkMode):
        return value
    if not isinstance(value, str):
        raise CriteriaValidationError("modalidade deve ser remoto, presencial ou híbrido.")
    text = unicodedata.normalize("NFKD", value.strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    aliases = {"remoto": WorkMode.REMOTE, "presencial": WorkMode.ONSITE, "hibrido": WorkMode.HYBRID}
    try:
        return aliases[text]
    except KeyError:
        raise CriteriaValidationError("modalidade deve ser remoto, presencial ou híbrido.") from None


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    """Critérios tipados, imutáveis e independentes de persistência."""

    professional_area: str | None = None
    desired_title: str | None = None
    work_mode: WorkMode | None = None
    location: str | None = None
    seniority: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    skills: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("professional_area", "desired_title", "location", "seniority"):
            object.__setattr__(self, name, _normalize_text(name, getattr(self, name)))

        object.__setattr__(self, "work_mode", _normalize_work_mode(self.work_mode))
        salary_min = _normalize_salary("salary_min", self.salary_min)
        salary_max = _normalize_salary("salary_max", self.salary_max)
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise CriteriaValidationError("salary_min não pode ser maior que salary_max.")
        object.__setattr__(self, "salary_min", salary_min)
        object.__setattr__(self, "salary_max", salary_max)

        if self.skills is None:
            object.__setattr__(self, "skills", ())
        if isinstance(self.skills, str) or not isinstance(self.skills, (tuple, list)):
            raise CriteriaValidationError("skills deve ser uma lista ou tupla de textos.")
        normalized_skills: list[str] = []
        seen: set[str] = set()
        for skill in self.skills:
            normalized = _normalize_text("skill", skill)
            if normalized and normalized.casefold() not in seen:
                normalized_skills.append(normalized)
                seen.add(normalized.casefold())
        object.__setattr__(self, "skills", tuple(normalized_skills))

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SearchCriteria":
        """Valida um dicionário, útil nas fronteiras com arquivos ou futuras APIs."""
        allowed = set(cls.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise CriteriaValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        """Retorna valores simples, adequados à futura camada de persistência."""
        result = asdict(self)
        result["work_mode"] = self.work_mode.value if self.work_mode else None
        result["salary_min"] = str(self.salary_min) if self.salary_min is not None else None
        result["salary_max"] = str(self.salary_max) if self.salary_max is not None else None
        result["skills"] = list(self.skills)
        return result
