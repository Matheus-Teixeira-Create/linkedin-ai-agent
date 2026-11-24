"""Modelos validados das informações profissionais de uma pessoa candidata."""

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class ProfileValidationError(ValueError):
    """Indica dados inválidos no perfil profissional."""


class Proficiency(str, Enum):
    """Níveis de proficiência aceitos para idiomas."""

    BASIC = "básico"
    INTERMEDIATE = "intermediário"
    ADVANCED = "avançado"
    FLUENT = "fluente"
    NATIVE = "nativo"


def _text(value: Any, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ProfileValidationError(f"{field} é obrigatório.")
        return None
    if not isinstance(value, str):
        raise ProfileValidationError(f"{field} deve ser um texto.")
    value = value.strip()
    if not value and required:
        raise ProfileValidationError(f"{field} é obrigatório.")
    return value or None


def _date(value: date | str | None, field: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ProfileValidationError(f"{field} deve ser uma data no formato AAAA-MM-DD.")


def _date_order(start: date | None, end: date | None, field: str) -> None:
    if start and end and end < start:
        raise ProfileValidationError(f"A data final de {field} não pode anteceder a data inicial.")


def _unique_texts(values: Any, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise ProfileValidationError(f"{field} deve ser uma lista de textos.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value, field)
        if text and text.casefold() not in seen:
            result.append(text)
            seen.add(text.casefold())
    return tuple(result)


def _url(value: Any) -> str | None:
    value = _text(value, "URL")
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        raise ProfileValidationError("A URL deve usar http ou https e conter um domínio válido.")
    return value


@dataclass(frozen=True, slots=True)
class Education:
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | str | None = None
    end_date: date | str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "institution", _text(self.institution, "institution", True))
        for field in ("degree", "field_of_study", "description"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        start, end = _date(self.start_date, "start_date"), _date(self.end_date, "end_date")
        _date_order(start, end, "education")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)


@dataclass(frozen=True, slots=True)
class Experience:
    organization: str
    role: str
    start_date: date | str | None = None
    end_date: date | str | None = None
    description: str | None = None
    is_current: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "organization", _text(self.organization, "organization", True))
        object.__setattr__(self, "role", _text(self.role, "role", True))
        object.__setattr__(self, "description", _text(self.description, "description"))
        start, end = _date(self.start_date, "start_date"), _date(self.end_date, "end_date")
        _date_order(start, end, "experience")
        if self.is_current and end is not None:
            raise ProfileValidationError("Experiência atual não deve informar end_date.")
        if not isinstance(self.is_current, bool):
            raise ProfileValidationError("is_current deve ser booleano.")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)


@dataclass(frozen=True, slots=True)
class Language:
    name: str
    proficiency: Proficiency | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name", True))
        try:
            object.__setattr__(self, "proficiency", Proficiency(self.proficiency))
        except ValueError:
            raise ProfileValidationError("Nível de proficiência inválido.") from None


@dataclass(frozen=True, slots=True)
class Project:
    name: str
    description: str | None = None
    url: str | None = None
    start_date: date | str | None = None
    end_date: date | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name", True))
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(self, "url", _url(self.url))
        start, end = _date(self.start_date, "start_date"), _date(self.end_date, "end_date")
        _date_order(start, end, "project")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)


@dataclass(frozen=True, slots=True)
class CourseCertification:
    name: str
    issuer: str | None = None
    issue_date: date | str | None = None
    expiration_date: date | str | None = None
    credential_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "name", True))
        object.__setattr__(self, "issuer", _text(self.issuer, "issuer"))
        issued, expires = _date(self.issue_date, "issue_date"), _date(self.expiration_date, "expiration_date")
        _date_order(issued, expires, "certification")
        object.__setattr__(self, "issue_date", issued)
        object.__setattr__(self, "expiration_date", expires)
        object.__setattr__(self, "credential_url", _url(self.credential_url))


@dataclass(frozen=True, slots=True)
class ProfessionalLink:
    label: str
    url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _text(self.label, "label", True))
        normalized_url = _url(self.url)
        if normalized_url is None:
            raise ProfileValidationError("url é obrigatório.")
        object.__setattr__(self, "url", normalized_url)


@dataclass(frozen=True, slots=True)
class ProfessionalProfile:
    name: str | None = None
    professional_summary: str | None = None
    location: str | None = None
    technical_skills: tuple[str, ...] = ()
    behavioral_skills: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    education: tuple[Education, ...] = ()
    experience: tuple[Experience, ...] = ()
    languages: tuple[Language, ...] = ()
    projects: tuple[Project, ...] = ()
    courses_certifications: tuple[CourseCertification, ...] = ()
    links: tuple[ProfessionalLink, ...] = ()

    def __post_init__(self) -> None:
        for field in ("name", "professional_summary", "location"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        for field in ("technical_skills", "behavioral_skills", "technologies"):
            object.__setattr__(self, field, _unique_texts(getattr(self, field), field))
        entry_types = {
            "education": Education, "experience": Experience, "languages": Language,
            "projects": Project, "courses_certifications": CourseCertification, "links": ProfessionalLink,
        }
        for field, expected in entry_types.items():
            entries = getattr(self, field)
            if entries is None:
                object.__setattr__(self, field, ())
                entries = ()
            if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
                raise ProfileValidationError(f"{field} deve ser uma lista de registros.")
            normalized = tuple(_entry(expected, entry, field) for entry in entries)
            object.__setattr__(self, field, _deduplicate_entries(normalized, field))

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "ProfessionalProfile":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise ProfileValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
        nested = {
            "education": Education, "experience": Experience, "languages": Language,
            "projects": Project, "courses_certifications": CourseCertification, "links": ProfessionalLink,
        }
        converted = dict(values)
        for field, model in nested.items():
            if field in converted and converted[field] is None:
                converted[field] = ()
            elif field in converted:
                entries = converted[field]
                if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
                    raise ProfileValidationError(f"{field} deve ser uma lista de registros.")
                converted[field] = [_entry(model, entry, field) for entry in converted[field]]
        return cls(**converted)

    def to_dict(self) -> dict[str, Any]:
        """Converte enums e datas para valores simples, prontos para persistência futura."""
        return _plain(asdict(self))


def _entry(model: type, value: Any, field: str) -> Any:
    if isinstance(value, model):
        return value
    if isinstance(value, dict):
        try:
            return model(**value)
        except TypeError as error:
            raise ProfileValidationError(f"Registro inválido em {field}: {error}.") from None
    raise ProfileValidationError(f"Cada item de {field} deve ser um registro válido.")


def _deduplicate_entries(entries: tuple[Any, ...], field: str) -> tuple[Any, ...]:
    result, seen = [], set()
    for entry in entries:
        if isinstance(entry, Language):
            key = entry.name.casefold()
        elif isinstance(entry, ProfessionalLink):
            key = entry.url.casefold()
        elif isinstance(entry, Education):
            key = (type(entry), entry.institution.casefold(), (entry.degree or "").casefold(), (entry.field_of_study or "").casefold())
        elif isinstance(entry, Experience):
            key = (type(entry), entry.organization.casefold(), entry.role.casefold(), entry.start_date)
        elif isinstance(entry, Project):
            key = (type(entry), entry.name.casefold())
        elif isinstance(entry, CourseCertification):
            key = (type(entry), entry.name.casefold(), (entry.issuer or "").casefold())
        else:
            raise ProfileValidationError(f"Registro inválido em {field}.")
        if key not in seen:
            result.append(entry)
            seen.add(key)
    return tuple(result)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value
