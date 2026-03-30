from enum import Enum
from pathlib import Path

from src._admin_helper_cli.logger import LoggerSettings
from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings

MODULE_IMPORT_STRING = "admin_helper_cli.modules"
MODULES_PATHS = Path(__file__).parent
if not MODULES_PATHS.is_dir():
    raise NotADirectoryError(
        f"Modules path '{MODULES_PATHS}' is not a directory.")


class _Settings(BaseSettings):
    ...


class BaseModuleSettings(BaseModel):
    class Type(str, Enum):
        ...

    type: Type = Field(default=...,
                       title="Module type",
                       description="The type of the module")
    name: str = Field(default=...,
                      title="Module name",
                      description="The name of the module")
    enabled: bool = Field(default=True,
                          title="Module enabled",
                          description="Whether the module is enabled")
    title: str | None = Field(default=None,
                              title="Module title",
                              description="The title of the module")
    description: str | None = Field(default=None,
                                    title="Module description",
                                    description="The description of the module")
    path: str | None = Field(default=None,
                             title="Module path",
                             description="The path to the module")
    entry_point: str | None = Field(default="__main__:main",
                                    title="Module entry point",
                                    description="The entry point of the module")
    logger: LoggerSettings = Field(default_factory=LoggerSettings,
                                   title="Logger settings",
                                   description="Settings for the logger")

    @computed_field(title="Module path", description="The path to the module")
    def module_path(self) -> Path:
        return MODULES_PATHS / self.name

    @computed_field(title="Full module entry point", description="The full module entry point")
    def full_entry_point(self) -> str:
        return f"{MODULE_IMPORT_STRING}.{self.name}.{self.entry_point}"
    
    @computed_field(title="traefik_templates_path", description="The path to the Traefik templates of the module")
    def traefik_templates_path(self) -> Path:
        return self.module_path / "traefik"
    
    @computed_field(title="supervisor_templates_path", description="The path to the Supervisor templates of the module")
    def supervisor_templates_path(self) -> Path:
        return self.module_path / "supervisor"
    
    @computed_field(title="static_settings", description="The static settings of the module")
    def static_settings(self) -> _Settings:
        raise NotImplementedError("The static settings of the module must be implemented in the module itself.")
