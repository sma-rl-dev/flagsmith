# Deploy-time bootstrap: the SPA loads its own feature flags through the
# flagsmith JS client (frontend/common/stores/config-store.js) and renders the
# Maintenance page when that call errors, so point it at an environment that
# exists in this instance. Run inside the app container after migrations:
#   python manage.py shell -c "exec(open('/tmp/bootstrap.py').read())"
from environments.models import Environment
from organisations.models import Organisation
from projects.models import Project

API_KEY = "testerenvplatformflags0000000001"

organisation, _ = Organisation.objects.get_or_create(name="Tester Env Platform")
project, _ = Project.objects.get_or_create(
    organisation=organisation, name="Platform Configuration"
)
environment, created = Environment.objects.get_or_create(
    project=project, name="Default", defaults={"api_key": API_KEY}
)
if environment.api_key != API_KEY:
    environment.api_key = API_KEY
    environment.save()

print(f"platform-flags environment ready (api_key={environment.api_key}, created={created})")
