"""Modelos validados para representar requisitos declarados de uma vaga."""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from app.models.professional_profile import Proficiency


class VacancyValidationError(ValueError):
    """Indica que os dados de uma vaga ou requisito são inválidos."""


class RequirementCategory(str, Enum):
    """Categorias comparáveis com as informações do perfil profissional."""

    SKILL = "competencia"
    EXPERIENCE = "experiencia"
    EDUCATION = "formacao"
    LANGUAGE = "idioma"


class RequirementImportance(str, Enum):
    """Importância declarada do requisito na vaga."""

    REQUIRED = "obrigatorio"
    DESIRABLE = "desejavel"


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VacancyValidationError(f"{field} deve ser um texto não vazio.")
    return value.strip()


def _optional_years(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise VacancyValidationError("minimum_years deve ser um número não negativo.")
    try:
        years = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise VacancyValidationError("minimum_years deve ser um número não negativo.") from None
    if not years.is_finite() or years < 0:
        raise VacancyValidationError("minimum_years deve ser um número não negativo.")
    return years


@dataclass(frozen=True, slots=True)
class JobRequirement:
    """Um requisito verificável, marcado como obrigatório ou desejável.

    Para requisitos de idioma, ``minimum_proficiency`` pode indicar o nível
    mínimo. Para experiência, ``minimum_years`` pode indicar a duração mínima.
    """

    category: RequirementCategory | str
    description: str
    importance: RequirementImportance | str = RequirementImportance.REQUIRED
    minimum_proficiency: Proficiency | str | None = None
    minimum_years: Decimal | int | float | str | None = None

    def __post_init__(self) -> None:
        try:
            category = RequirementCategory(self.category)
            importance = RequirementImportance(self.importance)
        except (ValueError, TypeError):
            raise VacancyValidationError("Categoria ou importância de requisito inválida.") from None
        description = _required_text(self.description, "description")
        proficiency = self.minimum_proficiency
        if proficiency is not None:
            if category is not RequirementCategory.LANGUAGE:
                raise VacancyValidationError("minimum_proficiency só pode ser usado em requisitos de idioma.")
            try:
                proficiency = Proficiency(proficiency)
            except (ValueError, TypeError):
                raise VacancyValidationError("Nível mínimo de proficiência inválido.") from None

        minimum_years = _optional_years(self.minimum_years)
        if minimum_years is not None and category is not RequirementCategory.EXPERIENCE:
            raise VacancyValidationError("minimum_years só pode ser usado em requisitos de experiência.")

        object.__setattr__(self, "category", category)
        object.__setattr__(self, "importance", importance)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "minimum_proficiency", proficiency)
        object.__setattr__(self, "minimum_years", minimum_years)


@dataclass(frozen=True, slots=True)
class JobVacancy:
    """Representação independente e sem persistência de uma vaga."""

    title: str
    professional_area: str | None = None
    requirements: tuple[JobRequirement, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        area = self.professional_area
        if area is not None:
            if not isinstance(area, str):
                raise VacancyValidationError("professional_area deve ser um texto ou None.")
            area = area.strip() or None
        object.__setattr__(self, "professional_area", area)

        requirements = self.requirements
        if requirements is None:
            requirements = ()
        if isinstance(requirements, (str, bytes)) or not isinstance(requirements, (list, tuple)):
            raise VacancyValidationError("requirements deve ser uma lista de requisitos.")
        normalized: list[JobRequirement] = []
        seen: set[tuple[Any, ...]] = set()
        for requirement in requirements:
            item = _requirement(requirement)
            key = (
                item.category,
                item.description.casefold(),
                item.importance,
                item.minimum_proficiency,
                item.minimum_years,
            )
            if key not in seen:
                normalized.append(item)
                seen.add(key)
        object.__setattr__(self, "requirements", tuple(normalized))

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "JobVacancy":
        if not isinstance(values, dict):
            raise VacancyValidationError("values deve ser um dicionário.")
        allowed = set(cls.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise VacancyValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
        converted = dict(values)
        if "requirements" in converted and converted["requirements"] is not None:
            requirements = converted["requirements"]
            if isinstance(requirements, (str, bytes)) or not isinstance(requirements, (list, tuple)):
                raise VacancyValidationError("requirements deve ser uma lista de requisitos.")
            converted["requirements"] = tuple(_requirement(item) for item in requirements)
        try:
            return cls(**converted)
        except TypeError:
            raise VacancyValidationError("Campos obrigatórios ausentes ou inválidos na vaga.") from None

    def to_dict(self) -> dict[str, Any]:
        """Converte enums e valores numéricos para dados simples."""
        result = asdict(self)
        result["requirements"] = [
            {
                **asdict(requirement),
                "category": requirement.category.value,
                "importance": requirement.importance.value,
                "minimum_proficiency": (
                    requirement.minimum_proficiency.value if requirement.minimum_proficiency else None
                ),
                "minimum_years": str(requirement.minimum_years) if requirement.minimum_years is not None else None,
            }
            for requirement in self.requirements
        ]
        return result


def _requirement(value: Any) -> JobRequirement:
    if isinstance(value, JobRequirement):
        return value
    if isinstance(value, dict):
        try:
            return JobRequirement(**value)
        except TypeError:
            raise VacancyValidationError("Registro de requisito contém campos ausentes ou desconhecidos.") from None
    raise VacancyValidationError("Cada item de requirements deve ser um requisito válido.")
