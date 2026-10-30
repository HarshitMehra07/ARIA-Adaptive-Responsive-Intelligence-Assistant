from automation.computer_use import ComputerUseService
from automation.policy import AutomationPolicyError, resolve_application_name


class AutomationController:
    """Compatibility entry point for explicit allowlisted application launches."""

    _service: ComputerUseService | None = None

    @classmethod
    def execute_command(cls, command_type: str, params: dict) -> bool:
        if command_type != "open_application" or not isinstance(params, dict):
            raise AutomationPolicyError("Only allowlisted application launches are supported.")
        app_name = params.get("app_name")
        if not isinstance(app_name, str):
            raise AutomationPolicyError("Name one supported application to open.")
        application = resolve_application_name(app_name)
        if cls._service is None:
            cls._service = ComputerUseService()
        result = cls._service.handle(f"open {application}")
        if result is None or result.requires_confirmation:
            raise AutomationPolicyError("The application launch could not be safely completed.")
        return result.attempted and result.verified

    @classmethod
    def close(cls) -> None:
        if cls._service is not None:
            cls._service.close()
            cls._service = None
