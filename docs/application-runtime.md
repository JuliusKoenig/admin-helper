# Application Runtime Design

This document records the agreed direction for turning the current static object registry into an embeddable, dynamic application runtime. The existing refactoring checklist remains separate in `docs/refactoring-checklist.md`.

## Current implementation phase

Phase 1 introduces `Application` as the public facade around the existing internal object registry. This phase intentionally preserves existing behavior:

- registrations are still collected before the initial build;
- `build()` delegates to the existing `instantiate_all()` implementation;
- the legacy module-level `register` decorator and `object_registry` remain available;
- no dynamic create, stop, destroy, event, scheduler, or plugin behavior is introduced yet.

The default public `application` wraps the existing `object_registry`, so both APIs address the same definitions and runtime instances.

Phase 1 isolates registration records and lookup indexes for separately constructed `Application` instances. The existing formatting and sensitive-value runtime bindings are still global and remain bound to the default application; complete multi-application configuration isolation is deferred to a later runtime refactoring.

## Target architecture

The intended high-level structure is:

```text
Application
├── ObjectRegistry
│   ├── object definitions
│   ├── runtime indexes
│   └── parent/name consistency
├── LifecycleController
├── EventBus
├── Scheduler
└── included Blueprints
```

`Application` is the user-facing runtime. The registry remains an internal utility responsible for registration records, object indexes, name resolution, and tree consistency.

## Application API direction

The initial facade exposes:

```python
app = Application()

@app.register(name="service")
class Service(BaseObject):
    pass

app.build()
service = app.get_by_name("service")
```

The default compatibility API remains:

```python
from admin_helper.objects import application, object_registry, register
```

Future lifecycle operations are planned as distinct methods rather than one overloaded build operation:

```python
await app.build()
await app.start()
await app.create(...)
await app.stop(...)
await app.destroy(...)
await app.shutdown()
```

`Application.exec()` is planned as the blocking standalone entry point that owns an asyncio loop. Embedded hosts such as FastAPI or NiceGUI will call the asynchronous lifecycle methods directly and retain ownership of their own loop. The runtime remains single-threaded by default.

## Application exit

Application-wide exit is planned as a control-flow exception derived from `BaseException`:

```python
raise AppExit(code=0, reason="Shutdown requested")
```

This prevents broad `except Exception` handlers from accidentally treating an intentional application exit as an ordinary failure. A host may catch the exit request, perform its own cleanup, and then decide whether to propagate or translate it.

## Object lifecycle

The object lifecycle will be strictly forward-only. Stopped objects cannot be started again, and a shut-down application cannot be restarted.

Planned lifecycle states:

```text
CREATED
→ INITIALIZING
→ READY
→ STARTING
→ RUNNING
→ STOPPING
→ STOPPED
→ DESTROYING
→ DESTROYED
```

`FAILED` records a failed lifecycle operation and preserves diagnostic data such as the exception, traceback, phase, and timestamp. Failed objects must still be cleanable.

Temporary activities will be separated from lifecycle state:

```text
IDLE
RECONFIGURING
MOVING
BROADCASTING
HANDLING_EVENT
```

An object can therefore be `RUNNING` while temporarily `RECONFIGURING`.

## Stop and destroy semantics

`STOPPED` is a diagnostic retention state. A stopped object no longer performs work but may remain indexed so its state, logs, and failure information can be inspected. A configurable policy may later destroy stopped objects immediately or replace a stopped object automatically when a new object needs the same name.

Destroying a parent is recursive. Stop and destroy traversal is child-first and reverses creation order among siblings. Parent cleanup runs only after all descendants have completed their cleanup.

`DESTROYED` means that the object has been detached from the managed runtime:

- removed from parent and indexes;
- event subscriptions and scheduled tasks removed;
- sensitive values deregistered;
- managed logger handlers closed;
- runtime references invalidated.

It does not guarantee immediate Python garbage collection because external references may still exist.

Cleanup will use explicit lifecycle hooks, not Python `__del__`. `atexit` may provide best-effort fallback cleanup, but explicit application shutdown remains authoritative.

## Lifecycle hooks and events

Each object will have well-known overridable lifecycle methods for its core behavior. Additional callbacks may be registered with decorators so multiple hooks can participate in the same phase.

Synchronous and asynchronous hooks are both accepted. They execute sequentially in the current thread. Synchronous hooks block the active event loop; asynchronous hooks yield only when they await. Lifecycle hooks are not launched as detached tasks because ordering must remain deterministic.

Lifecycle transitions are controlled centrally. Hooks run as part of the transition, and lifecycle events are emitted for external observers. Public events inform and extend the lifecycle but do not solely drive state transitions.

Timeouts and error policies may later be configurable. During tree shutdown, failures should normally be collected while cleanup continues for the remaining objects.

## Blueprints

A `Blueprint` is a named, declarative transport container for object definitions. It is comparable to a FastAPI router:

- it stores definitions before they are included;
- it may include other blueprints;
- it may carry a title, description, and future metadata;
- it is not a runtime object;
- created objects retain no reference to the blueprint.

An application includes a blueprint with an optional parent:

```python
app.include_blueprint(services, parent=container)
```

Root definitions from the blueprint are attached to the supplied parent. Without a parent they become application root objects. Internal parent relationships defined inside the blueprint remain intact.

Blueprint inclusion must support deterministic ordering, duplicate detection, and cycle detection. Nested blueprints are flattened into application registrations.

The application may internally retain registration-origin metadata so diagnostics or convenience queries can identify definitions and objects originating from a blueprint. This is metadata owned by the application, not a reference stored on each object. A blueprint itself has no load/unload lifecycle and no `BlueprintInstance` is planned.

## Import strings and future extensions

`ApplicationConfig` is planned to accept import targets using `module.path:attribute` syntax:

```text
my_project.objects:services_blueprint
```

Imports will be resolved during `build()`, not during `Application.__init__()`, to avoid constructor side effects. Imported targets are validated as blueprints and included before object construction.

A future `Extension` is a separate concept containing plugin metadata such as name, title, version, compatibility, and one or more blueprints. Extensions may later be loaded from explicit import strings or Python package entry points.

## Planned implementation order

1. Introduce `Application` as a facade around the existing registry.
2. Add named, nestable `Blueprint` definitions and parent-aware inclusion.
3. Introduce application and object lifecycle states plus validated transitions.
4. Add dynamic object creation, stopping, recursive destruction, and shutdown.
5. Add lifecycle hooks and the event system.
6. Add scheduler support for interval callbacks and object loops.
7. Add configuration-based blueprint loading and the extension/plugin layer.
