from ipaddress import IPv4Address
from pathlib import Path

from pydantic import BaseModel, Field, DirectoryPath


class TraefikSettings(BaseModel):
    path: DirectoryPath = Field(default=...,
                                title="Traefik path",
                                description="The path to the Traefik directory")
    version: str = Field(default=...,
                         title="Traefik version",
                         description="The version of Traefik to use")
    binary_name: str = Field(default=...,
                             title="Traefik binary name",
                             description="The name of the Traefik binary")
    host: IPv4Address = Field(default=...,
                              title="Traefik host",
                              description="The host of the Traefik")
    port: int = Field(default=...,
                      ge=1,
                      le=65535,
                      title="Traefik port",
                      description="The port of the Traefik")
    
    
    @property
    def binary_path(self) -> Path:
        binary_path: Path = self.path / self.binary_name
        if not binary_path.is_file():
            raise FileNotFoundError(f"Traefik binary not found at {binary_path}")
        return binary_path