import encodings
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import IO, Any

from pydantic import Field, BaseModel, field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src._admin_helper_cli.modules.filebrowser.settings import FileBrowserModuleSettings
from src._admin_helper_cli.modules.ttyd.settings import TtydModuleSettings

ModuleSettings = FileBrowserModuleSettings | TtydModuleSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_",
                                      env_nested_delimiter="__")
    
    class User(BaseModel):
        password: str = Field(..., title="Password",
                              description="The password of the user")
        is_admin: bool = Field(
            default=False, title="Is Admin", description="Whether the user is an admin")

    users: dict[str, User] = Field(default_factory=dict,
                                   title="Users",
                                   description="List of users")

    modules: list[ModuleSettings] = Field(default_factory=list,
                                          title="Modules",
                                          description="List of modules")

    @computed_field(title="Enabled modules", description="List of enabled modules")
    def modules_enabled(self) -> list[ModuleSettings]:
        return [module for module in self.modules if module.enabled]

    def get_module(self, name: str) -> ModuleSettings | None:
        for module in self.modules:
            if module.name == name:
                return module
        return None

settings = Settings()
