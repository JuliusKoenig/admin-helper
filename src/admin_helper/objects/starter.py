from dataclasses import dataclass

from admin_helper.objects.base import BaseObject


@dataclass
class StartObject(BaseObject,
                  abstract=True):
    def start(self) -> None:
        self.broadcast_call("start")