class ConfigurationError(RuntimeError):
    """Некорректная конфигурация."""


class ExternalServiceError(RuntimeError):
    """Безопасная ошибка внешнего сервиса без секретов."""

    def __init__(self, message: str, *, status_code: int | None = None, metadata: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.metadata = metadata or {}


class LiveModeRequired(PermissionError):
    """Изменяющая операция запрещена политикой безопасности."""


class ConfirmationRequired(PermissionError):
    """Операция не получила подтверждение пользователя."""


class ContractNotVerified(RuntimeError):
    """Контракт внешнего API не подтверждён для production-вызова."""
