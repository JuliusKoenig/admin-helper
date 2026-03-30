from ipaddress import IPv4Address
from pathlib import Path

from pydantic import Field, DirectoryPath, computed_field
from pydantic_settings import SettingsConfigDict

from src._admin_helper_cli.modules.settings import _Settings, BaseModuleSettings


class FileBrowserSettings(_Settings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_FILE_BROWSER_",
                                      env_nested_delimiter="__")
    
    version: str = Field(default=...,
                            title="FileBrowser version",
                            description="The version of FileBrowser to use")
    path: DirectoryPath = Field(default=...,
                                title="FileBrowser path",
                                description="The path to the FileBrowser directory")
    binary_name: str = Field(default=...,
                                title="FileBrowser binary name",
                                description="The name of the FileBrowser binary")
    
    @computed_field(title="FileBrowser binary path", description="The path to the FileBrowser binary")
    def binary_path(self) -> Path:
        binary_path: Path = self.path / self.binary_name
        if not binary_path.is_file():
            raise FileNotFoundError(
                f"FileBrowser binary not found at {binary_path}")
        return binary_path
    
file_browser_settings = FileBrowserSettings()


class FileBrowserModuleSettings(BaseModuleSettings):
    class Type(BaseModuleSettings.Type):
        FILE_BROWSER = "filebrowser"
    
    type: Type = Field(default=...,
                      title="Module type",
                      description="The type of the module")
    
    host: IPv4Address = Field(default=IPv4Address("127.0.0.1"),
                              title="File Browser host",
                              description="The host to use for the File Browser module")
    port: int = Field(default=8002,
                        title="File Browser port",
                        description="The port to use for the File Browser module")
    
    @computed_field(title="static_settings", description="The static settings of the module")
    def static_settings(self) -> FileBrowserSettings:
        return file_browser_settings