"""Serviço em memória para gerenciar o perfil profissional."""

from dataclasses import fields
from typing import Any

from app.models.professional_profile import ProfessionalProfile, ProfileValidationError


class ProfessionalProfileService:
    """Consulta e altera um perfil sem persistência ou integração externa."""

    _FIELD_NAMES = frozenset(field.name for field in fields(ProfessionalProfile))

    def __init__(self, profile: ProfessionalProfile | None = None) -> None:
        self._profile = profile or ProfessionalProfile()

    @property
    def get_profile(self) -> ProfessionalProfile:
        """Retorna o perfil atual, imutável."""
        return self._profile

    def create(self, profile: ProfessionalProfile | dict[str, Any]) -> ProfessionalProfile:
        return self.replace(profile)

    def update(self, **changes: Any) -> ProfessionalProfile:
        self._validate_fields(changes)
        values = self._profile.to_dict()
        values.update(changes)
        self._profile = ProfessionalProfile.from_dict(values)
        return self._profile

    def replace(self, profile: ProfessionalProfile | dict[str, Any]) -> ProfessionalProfile:
        if isinstance(profile, ProfessionalProfile):
            self._profile = profile
        elif isinstance(profile, dict):
            self._profile = ProfessionalProfile.from_dict(profile)
        else:
            raise ProfileValidationError("profile deve ser ProfessionalProfile ou um dicionário.")
        return self._profile

    def remove(self, field_name: str, index: int | None = None) -> ProfessionalProfile:
        self._validate_fields({field_name: None})
        values = self._profile.to_dict()
        current = values[field_name]
        if isinstance(current, list):
            if index is None:
                values[field_name] = []
            else:
                try:
                    values[field_name] = current[:index] + current[index + 1 :]
                except TypeError:
                    raise ProfileValidationError("index deve ser um número inteiro.") from None
                if index < 0 or index >= len(current):
                    raise ProfileValidationError("index está fora do intervalo.")
        elif index is not None:
            raise ProfileValidationError("index só pode ser usado para campos com vários registros.")
        else:
            values[field_name] = None
        self._profile = ProfessionalProfile.from_dict(values)
        return self._profile

    def clear(self) -> ProfessionalProfile:
        self._profile = ProfessionalProfile()
        return self._profile

    @staticmethod
    def _validate_fields(changes: dict[str, Any]) -> None:
        unknown = set(changes) - ProfessionalProfileService._FIELD_NAMES
        if unknown:
            raise ProfileValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
