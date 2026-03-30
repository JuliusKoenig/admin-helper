from ipaddress import IPv4Address

from pydantic import BaseModel, Field


class DashboardSettings(BaseModel):
        host: IPv4Address = Field(default=IPv4Address("127.0.0.1"),
                                  title="Dashboard host",
                                  description="The host of the dashboard")
        port: int = Field(default=8000,
                          ge=1,
                          le=65535,
                          title="Dashboard port",
                          description="The port of the dashboard")
        # workers: int = Field(default=2,
        #                     ge=1,
        #                     title="Dashboard workers",
        #                     description="The number of workers for the dashboard")