from ipaddress import IPv4Address
from pathlib import Path

from pydantic import Field, DirectoryPath, computed_field
from pydantic_settings import SettingsConfigDict

from src._admin_helper_cli.modules.settings import _Settings, BaseModuleSettings

class TtydSettings(_Settings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_HELPER_TTYD_",
                                      env_nested_delimiter="__")
    version: str = Field(default=...,
                            title="ttyd version",
                            description="The version of ttyd to use")
    path: DirectoryPath = Field(default=...,
                                title="ttyd path",
                                description="The path to the ttyd directory")
    binary_name: str = Field(default=...,
                                title="ttyd binary name",
                                description="The name of the ttyd binary")
    
    @computed_field(title="ttyd binary path", description="The path to the ttyd binary")
    def binary_path(self) -> Path:
        binary_path: Path = self.path / self.binary_name
        if not binary_path.is_file():
            raise FileNotFoundError(
                f"ttyd binary not found at {binary_path}")
        return binary_path
        
ttyd_settings = TtydSettings()


class TtydModuleSettings(BaseModuleSettings):
    class Type(BaseModuleSettings.Type):
        TTYD = "ttyd"
    
    type: Type = Field(default=...,
                      title="Module type",
                      description="The type of the module")
    host: IPv4Address = Field(default=IPv4Address("0.0.0.0"),
                              title="Ttyd host",
                              description="The host to use for the Ttyd module")
    port: int = Field(default=8001,
                        title="Ttyd port",
                        description="The port to use for the Ttyd module")
    shell: str = Field(default="bash",
                       title="Ttyd shell",
                       description="The shell to use for the Ttyd module")
    
    @computed_field(title="static_settings", description="The static settings of the module")
    def static_settings(self) -> TtydSettings:
        return ttyd_settings