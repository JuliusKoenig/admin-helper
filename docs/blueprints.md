# Blueprints

A `Blueprint` is a named declarative collection of object definitions. It is comparable to a FastAPI router: it stores definitions temporarily and transfers them into an `Application`, but it does not become part of the runtime object tree.

## Declaring a blueprint

```python
from admin_helper.objects import BaseObject, Blueprint

services = Blueprint(
    "services",
    title="Application services",
    description="Provides the service objects used by the application.",
)


@services.register(name="service")
class Service(BaseObject):
    pass
```

`Blueprint.register()` performs the same framework-compatible dataclass transformation and field validation as `Application.register()`. It does not register the class in an application immediately.

## Nested blueprints

Blueprints may include other blueprints:

```python
infrastructure = Blueprint("infrastructure")
infrastructure.include(services)
```

Nested includes are resolved depth-first in declaration order. Reusing the same blueprint instance through multiple include paths does not duplicate its definitions. Recursive include graphs are rejected.

## Including a blueprint in an application

```python
from admin_helper.objects import Application

app = Application()
app.include_blueprint(infrastructure)
app.build()
```

Without an explicit parent, all root definitions in the resolved blueprint graph become application roots.

A parent reference can be supplied before the build:

```python
@app.register(name="container")
class Container(BaseObject):
    pass

app.include_blueprint(infrastructure, parent=Container)
```

Only blueprint root definitions receive the supplied parent. Parent relationships declared inside a blueprint remain unchanged.

## Runtime semantics

After inclusion, normal application registrations and runtime objects are created. Runtime objects do not retain a reference to the blueprint. The blueprint has no load, unload, stop, or destroy lifecycle of its own.

The application retains optional origin metadata for diagnostics:

```python
app.get_blueprint("services")
app.blueprints_for_class(Service)
```

This metadata is owned by the application and is not stored on `Service` instances.

## Validation

Before changing the registry, inclusion validates the complete incoming graph:

- blueprint names are unique inside the application;
- include cycles are rejected;
- registration names do not conflict;
- a class is not registered more than once;
- repeated inclusion uses the same parent binding;
- inclusion currently occurs only before `Application.build()`.

This keeps blueprint inclusion transactional: a rejected graph leaves no partial registrations behind.
