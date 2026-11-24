"""Serviço em memória para consultar e alterar critérios de busca."""

from dataclasses import fields
from typing import Any

from app.models.search_criteria import CriteriaValidationError, SearchCriteria


class SearchCriteriaService:
    """Gerencia um conjunto de critérios sem dependência de banco de dados."""

    _FIELD_NAMES = frozenset(field.name for field in fields(SearchCriteria))

    def __init__(self, initial: SearchCriteria | None = None) -> None:
        self._criteria = initial or SearchCriteria()

    @property
    def current(self) -> SearchCriteria:
        """Retorna os critérios atuais, que são imutáveis."""
        return self._criteria

    def update(self, **changes: Any) -> SearchCriteria:
        """Atualiza somente os campos informados; None limpa um campo."""
        unknown = set(changes) - self._FIELD_NAMES
        if unknown:
            raise CriteriaValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
        values = self._criteria.to_dict()
        values.update(changes)
        self._criteria = SearchCriteria.from_dict(values)
        return self._criteria

    def replace(self, criteria: SearchCriteria | dict[str, Any]) -> SearchCriteria:
        """Substitui todos os critérios por um modelo ou dicionário validado."""
        if isinstance(criteria, SearchCriteria):
            self._criteria = criteria
        elif isinstance(criteria, dict):
            self._criteria = SearchCriteria.from_dict(criteria)
        else:
            raise CriteriaValidationError("criteria deve ser SearchCriteria ou um dicionário.")
        return self._criteria

    def clear(self, *field_names: str) -> SearchCriteria:
        """Limpa todos os critérios ou somente os campos indicados."""
        selected = set(field_names) if field_names else set(self._FIELD_NAMES)
        unknown = selected - self._FIELD_NAMES
        if unknown:
            raise CriteriaValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
        empty_values = {name: ([] if name == "skills" else None) for name in selected}
        return self.update(**empty_values)
