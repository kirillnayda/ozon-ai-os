class ConfigurationError(RuntimeError):
    """Некорректная конфигурация."""


class ExternalServiceError(RuntimeError):
    """Безопасная ошибка внешнего сервиса без секретов."""


class LiveModeRequired(PermissionError):
    """Изменяющая операция запрещена политикой безопасности."""


class ConfirmationRequired(PermissionError):
    """Операция не получила подтверждение пользователя."""


class ContractNotVerified(RuntimeError):
    """Контракт внешнего API не подтверждён для production-вызова."""

