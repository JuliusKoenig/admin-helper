from dataclasses import dataclass

from admin_helper.settings import AdminHelperSettings
from admin_helper.objects.admin_helper.supervisor.main import Supervisor
from admin_helper.objects.admin_helper.apache.route import ReverseProxyApacheRoute


@dataclass
class SupervisorDashboard(ReverseProxyApacheRoute,
                      name="supervisor_dashboard",
                      parent=Supervisor,
                      path="/supervisor",
                      target_url=f"http://{AdminHelperSettings.supervisor.dashboard_host}:{AdminHelperSettings.supervisor.dashboard_port}",
                      auth_required=False):
    ...


SupervisorDashboard: SupervisorDashboard = SupervisorDashboard()