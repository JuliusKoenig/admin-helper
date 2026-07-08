from dataclasses import dataclass

from admin_helper.objects import BaseObject


@dataclass
class AdminHelper(BaseObject):
    def start(self) -> None:
        self.broadcast_call("start")

    def test(self) -> dict[str, tuple[bool, str]]:
        result = {}
        for broadcast_result in self.broadcast_call("test"):
            result.update(broadcast_result)
        return result

    def render(self) -> dict[str, tuple[bool, str]]:
        result = {}
        for broadcast_result in self.broadcast_call("render"):
            result.update(broadcast_result)
        return result


AdminHelper = AdminHelper()
