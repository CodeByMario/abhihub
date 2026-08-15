# AbhiHub Route Dependency Mapping Agent

## 1. Purpose

The **AbhiHub Route Dependency Mapping Agent** is a code-analysis agent
whose job is to inspect `app.py`, discover **every possible application
route**, and generate a Markdown file containing a precise dependency
map for each route.

The generated Markdown must answer:

> **For this route, exactly which files, functions, classes, imports,
> configuration values, templates, static assets, database operations,
> middleware, and external services are required for the route to load
> and execute?**

The agent must be conservative and evidence-based.

It must not guess dependencies merely because a file appears related.

------------------------------------------------------------------------

# 2. Primary Output

The agent generates:

``` text
ROUTES.md
```

or, if the project specifies another filename:

``` text
route-map.md
```

The output must contain:

1.  Every discovered route.
2.  HTTP method(s).
3.  Route path.
4.  Route registration location.
5.  Route handler.
6.  Complete relevant dependency chain.
7.  Exact file paths.
8.  Exact line numbers or line ranges.
9.  Why each dependency is required.
10. Dependency type.
11. Any dynamic or uncertain dependency.
12. External services used by the route.
13. Database interactions.
14. Templates and static files.
15. Middleware and decorators affecting the route.
16. Configuration and environment variables.
17. Error handlers involved.
18. A confidence level for every dependency.

------------------------------------------------------------------------

# 3. Critical Requirement

The agent must distinguish between:

### Direct dependency

A file/function is directly referenced by the route.

``` text
app.py
  ↓
routes/users.py
```

### Transitive dependency

A dependency is required by another dependency.

``` text
app.py
  ↓
routes/users.py
  ↓
services/user_service.py
  ↓
repositories/user_repository.py
  ↓
database.py
```

### Runtime dependency

The dependency is not necessarily visible from a simple static import
but is required during execution.

Examples:

-   Middleware
-   Dependency injection
-   Plugin registration
-   Blueprint/router registration
-   Template loading
-   Configuration
-   Environment variables
-   Database connection
-   External API client

### Optional dependency

The route can execute without it under some conditions.

### Conditional dependency

The dependency is required only for a particular branch.

The agent must label these separately.

------------------------------------------------------------------------

# 4. Discovery Starting Point

The agent must begin with:

``` text
app.py
```

It should identify:

-   Flask/FastAPI/Django/Sanic/etc.
-   Application instance
-   Router/Blueprint registration
-   Route decorators
-   Included routers
-   Mounted applications
-   Middleware
-   Error handlers
-   Startup/shutdown handlers

It must not assume that every route is declared directly in `app.py`.

For example:

``` python
app.register_blueprint(user_routes)
```

must cause the agent to inspect the referenced blueprint.

Likewise:

``` python
app.include_router(users_router)
```

must cause recursive router discovery.

------------------------------------------------------------------------

# 5. Framework Detection

The agent should first determine which routing framework is being used.

Examples:

### Flask

Look for:

``` python
@app.route(...)
@blueprint.route(...)
app.register_blueprint(...)
```

### FastAPI

Look for:

``` python
@app.get(...)
@app.post(...)
@app.put(...)
@app.delete(...)
router.get(...)
router.post(...)
app.include_router(...)
```

### Django

Look for:

``` python
urlpatterns
path(...)
re_path(...)
include(...)
```

### Other frameworks

The agent should inspect framework-specific routing mechanisms rather
than relying only on hardcoded patterns.

------------------------------------------------------------------------

# 6. Route Discovery

For every route, record:

``` text
Route ID
HTTP Method
Path
Registration File
Registration Line
Handler
Handler File
Handler Line
Router / Blueprint
Prefix
Name
Tags
Authentication Requirement
```

Example:

``` markdown
## ROUTE-001

### Route

`GET /api/users/{user_id}`

### Registration

`app.py:42`

### Handler

`get_user`

### Handler Location

`routes/users.py:18-31`

### Router

`users_router`

### Authentication

Required

### Route Chain

app.py:42
→ routes/users.py:18
→ services/user_service.py:12
→ repositories/user_repository.py:27
→ database.py:41
```

------------------------------------------------------------------------

# 7. Complete Dependency Traversal

The agent must recursively follow dependencies.

For each route:

``` text
Route
 ↓
Handler
 ↓
Imported modules
 ↓
Called functions/classes
 ↓
Their dependencies
 ↓
Database / external services / templates
```

The traversal must continue until it reaches a meaningful runtime
boundary.

Examples of runtime boundaries:

-   Standard library
-   Stable third-party library internals
-   Operating-system primitives
-   External service APIs

The agent does not need to map every line inside a third-party package.

------------------------------------------------------------------------

# 8. Function-Level Analysis

Imports alone are insufficient.

Consider:

``` python
from services.users import get_user, delete_user
```

If the route only calls:

``` python
get_user(user_id)
```

the agent should not claim that `delete_user` is required.

It should distinguish:

``` text
Imported dependency
```

from:

``` text
Executed dependency
```

Whenever possible, the agent should follow actual call relationships.

------------------------------------------------------------------------

# 9. Class-Level Analysis

For classes, identify:

-   Constructor
-   Methods invoked
-   Inherited behavior
-   Mixins
-   Class decorators
-   Dependency injection
-   Configuration used by the class

Example:

``` text
routes/users.py:18
    ↓
UserService.__init__()      services/users.py:12
    ↓
UserRepository()            repositories/users.py:9
    ↓
Database.get_connection()   database.py:41
```

------------------------------------------------------------------------

# 10. Line-Level Accuracy

Every internal dependency must contain an exact line reference whenever
possible.

Preferred format:

``` text
src/services/user_service.py:42
```

For a larger required block:

``` text
src/services/user_service.py:42-67
```

If exact line numbers cannot be determined:

``` text
src/services/user_service.py
```

with:

``` text
Confidence: LOW
Reason: Dynamic execution prevents precise line mapping.
```

The agent must never invent line numbers.

------------------------------------------------------------------------

# 11. Why Each File Is Required

Every dependency must include a reason.

Example:

``` markdown
| File | Lines | Type | Why Required |
|---|---:|---|---|
| `routes/users.py` | 18-31 | Handler | Defines the route handler |
| `services/user_service.py` | 12-48 | Service | Retrieves user data |
| `repositories/user_repository.py` | 27-44 | Repository | Executes user query |
| `database.py` | 41-62 | Infrastructure | Creates database connection |
```

The explanation should be specific.

Bad:

``` text
Needed by the route.
```

Good:

``` text
Called by `UserService.get_user()` to retrieve the requested user record.
```

------------------------------------------------------------------------

# 12. Dependency Types

Use a controlled vocabulary.

``` text
ROUTE
HANDLER
FUNCTION
CLASS
IMPORT
MIDDLEWARE
AUTH
AUTHORIZATION
VALIDATION
SERVICE
REPOSITORY
DATABASE
MODEL
SCHEMA
CONFIG
ENVIRONMENT
TEMPLATE
STATIC_ASSET
SERIALIZER
EXTERNAL_API
QUEUE
CACHE
ERROR_HANDLER
STARTUP
SHUTDOWN
UTILITY
CONDITIONAL
OPTIONAL
UNKNOWN
```

------------------------------------------------------------------------

# 13. Middleware Mapping

Middleware is critical because a route may depend on code that is not
visible from the route handler.

The agent must identify middleware such as:

``` text
Authentication
Authorization
CORS
Logging
Rate limiting
Compression
Session handling
Tracing
Request ID
Error handling
```

Example:

``` markdown
### Middleware Chain

1. `middleware/auth.py:14-48`
   - Validates authentication token.

2. `middleware/request_id.py:8-21`
   - Adds request ID.

3. `middleware/error_handler.py:11-42`
   - Converts exceptions into HTTP responses.
```

------------------------------------------------------------------------

# 14. Authentication and Authorization

For each protected route, identify the exact security chain.

Example:

``` text
GET /api/projects/{id}
        ↓
auth_required()
        ↓
get_current_user()
        ↓
check_project_owner()
        ↓
ProjectService.get_project()
```

Record:

-   Authentication function
-   Authorization function
-   Permission checks
-   Role checks
-   Ownership checks
-   Relevant files and lines

This is especially important for security auditing.

------------------------------------------------------------------------

# 15. Request Validation

Identify all validation dependencies.

Examples:

``` text
Pydantic model
Marshmallow schema
WTForms
Custom validators
Manual validation functions
```

Example:

``` markdown
### Validation

`schemas/project.py:12-29`

Type:
`SCHEMA`

Purpose:
Validates project creation payload before the service layer executes.
```

------------------------------------------------------------------------

# 16. Database Dependency Mapping

For every route that accesses a database, map:

``` text
Route
 ↓
Service
 ↓
Repository
 ↓
ORM Model
 ↓
Database Session
 ↓
Database Configuration
```

Record:

-   Query function
-   ORM model
-   Tables/models accessed
-   Database session
-   Transaction handling
-   Connection configuration
-   Relevant line numbers

Example:

``` markdown
### Database Chain

`services/project_service.py:31`
→ `repositories/project_repository.py:44`
→ `models/project.py:7`
→ `database/session.py:18`
```

------------------------------------------------------------------------

# 17. External Service Mapping

Identify every external service called by the route.

Examples:

-   OpenAI
-   Stripe
-   AWS
-   Google APIs
-   Email provider
-   Payment gateway
-   Storage provider
-   Maps
-   Analytics

Record:

``` markdown
### External Services

#### OpenAI

Client:
`services/ai_client.py:12-54`

Called from:
`services/project_service.py:82`

Environment:
`OPENAI_API_KEY`

Purpose:
Generates project summary.
```

------------------------------------------------------------------------

# 18. Environment Variables

For every route, identify environment variables that can affect
execution.

Example:

``` markdown
### Environment Dependencies

| Variable | File | Lines | Purpose |
|---|---|---:|---|
| `DATABASE_URL` | `database.py` | 18 | Database connection |
| `JWT_SECRET` | `auth.py` | 11 | Token validation |
| `OPENAI_API_KEY` | `ai_client.py` | 9 | AI API authentication |
```

Never expose actual secret values.

Only document variable names.

------------------------------------------------------------------------

# 19. Configuration Mapping

Identify configuration dependencies such as:

``` text
settings.py
config.py
.env loading
feature flags
runtime configuration
deployment configuration
```

Example:

``` text
config/settings.py:20-58
```

Purpose:

``` text
Provides database and authentication configuration required by the route.
```

------------------------------------------------------------------------

# 20. Templates and Static Files

For server-rendered routes, identify:

-   Template files
-   Template inheritance
-   Included templates
-   Static CSS
-   JavaScript
-   Images
-   Fonts
-   Other required assets

Example:

``` text
GET /dashboard
 ↓
routes/dashboard.py:22
 ↓
templates/dashboard.html
 ↓
templates/base.html
 ↓
static/dashboard.js
 ↓
static/dashboard.css
```

The agent should recursively inspect template inheritance and includes.

------------------------------------------------------------------------

# 21. Error Handling

Identify route-specific and global error handlers.

Examples:

``` text
404 handler
401 handler
403 handler
422 handler
500 handler
Custom application exceptions
```

If the route can trigger a known custom exception, include the relevant
handler.

Example:

``` markdown
### Error Handling

`errors/project_errors.py:12-34`

Used when:
`ProjectNotFoundError` is raised.

Handler:
`app.py:91`
```

------------------------------------------------------------------------

# 22. Startup and Shutdown Dependencies

Some routes rely on resources initialized during application startup.

Examples:

``` text
Database connection pool
Redis connection
AI client
Message queue
Cache
Search index
```

The agent should map:

``` text
Startup
 ↓
Resource initialization
 ↓
Route
```

Example:

``` text
app.py:14
→ startup/database.py:8-29
→ database/session.py:18
→ routes/users.py:42
```

------------------------------------------------------------------------

# 23. Dynamic Dependencies

The agent must explicitly detect dynamic behavior.

Examples:

``` python
importlib.import_module(...)
```

``` python
getattr(...)
```

``` python
globals()[name]
```

Plugin systems:

``` python
load_plugins()
```

Dynamic routing:

``` python
register_route(...)
```

If the dependency graph cannot be proven statically, mark it:

``` text
Dynamic Dependency
Confidence: MEDIUM
```

and explain why.

------------------------------------------------------------------------

# 24. Conditional Dependencies

Example:

``` python
if settings.USE_AI:
    generate_summary()
```

The agent should document:

``` markdown
### Conditional Dependency

`services/ai.py:22-48`

Required when:

`USE_AI=true`

Not required when:

`USE_AI=false`
```

------------------------------------------------------------------------

# 25. Route Dependency Tree

Every route should have a visual dependency tree.

Example:

``` text
GET /api/projects/{id}

app.py:42
│
├── middleware/auth.py:14-48
│   └── auth/token.py:22-61
│
├── routes/projects.py:18-37
│   ├── schemas/project.py:12-29
│   ├── services/project_service.py:31-67
│   │   ├── repositories/project_repository.py:44-73
│   │   │   ├── models/project.py:7-41
│   │   │   └── database/session.py:18-39
│   │   │
│   │   └── services/cache.py:12-31
│   │
│   └── serializers/project.py:9-28
│
└── errors/project_errors.py:12-34
```

This tree is one of the most important outputs.

------------------------------------------------------------------------

# 26. Route Summary Table

At the beginning of the generated Markdown file, include a complete
route inventory.

``` markdown
| ID | Method | Route | Handler | File | Line | Auth | Dependencies |
|---|---|---|---|---|---:|---|---:|
| ROUTE-001 | GET | `/` | `home` | `routes/home.py` | 12 | No | 6 |
| ROUTE-002 | GET | `/users` | `list_users` | `routes/users.py` | 18 | Yes | 9 |
| ROUTE-003 | POST | `/users` | `create_user` | `routes/users.py` | 42 | Yes | 12 |
```

Every discovered route must appear in this table.

------------------------------------------------------------------------

# 27. Route Completeness Check

The agent must perform a second pass after generating the route
inventory.

It should ask:

``` text
Have all routes been discovered?
```

Cross-check:

-   Decorators
-   Router registrations
-   Blueprint registrations
-   Included routers
-   Nested routers
-   Mounted applications
-   Dynamic route registration
-   Framework-specific route tables

The final report must contain:

``` markdown
## Route Discovery Verification

Routes discovered: 37

Routes verified through framework registration: 36

Routes requiring manual/dynamic verification: 1

Discovery confidence: HIGH
```

------------------------------------------------------------------------

# 28. Orphaned Route Detection

The agent should identify routes that appear in source code but are not
registered.

Example:

``` text
Potential orphan route:

routes/admin.py:44

@router.get("/admin/users")

Status:
Handler exists, but router registration could not be found.

Confidence:
MEDIUM
```

This is useful for detecting dead code.

------------------------------------------------------------------------

# 29. Broken Dependency Detection

The agent should detect:

-   Missing imports
-   Missing files
-   Missing functions
-   Circular imports
-   Broken route references
-   Missing templates
-   Missing environment variables
-   Invalid configuration
-   Missing database models
-   Missing external clients

Example:

``` markdown
### BROKEN DEPENDENCY

Route:
`POST /api/users`

File:
`routes/users.py:54`

Problem:
Calls `UserService.create_user()`, but the referenced method does not exist.

Severity:
HIGH
```

------------------------------------------------------------------------

# 30. Circular Dependency Detection

The dependency graph must be checked for cycles.

Example:

``` text
A
 ↓
B
 ↓
C
 ↓
A
```

Report:

``` markdown
### Circular Dependency

`service_a.py`
→ `service_b.py`
→ `service_c.py`
→ `service_a.py`

Impact:
May cause import failures or unnecessary architectural coupling.
```

------------------------------------------------------------------------

# 31. Unused Route Dependency Detection

The agent should distinguish between:

``` text
Imported
```

and:

``` text
Actually required
```

If an imported dependency is not used by the route execution path, mark
it as:

``` text
Unused / non-essential dependency
```

This is useful for future optimization.

------------------------------------------------------------------------

# 32. Confidence Levels

Every route and dependency should receive:

### HIGH

Dependency was directly verified through static analysis and
call/reference tracing.

### MEDIUM

Dependency is strongly indicated but includes dynamic behavior.

### LOW

Dependency could not be conclusively resolved.

Example:

``` markdown
Confidence: HIGH

Evidence:
`routes/users.py:22` directly calls
`UserService.get_user()` defined at
`services/users.py:31`.
```

------------------------------------------------------------------------

# 33. Evidence Requirement

The agent must never claim a dependency without evidence.

Each dependency should have at least one evidence source:

``` text
IMPORT
CALL
REFERENCE
DECORATOR
REGISTRATION
CONFIGURATION
TEMPLATE_REFERENCE
RUNTIME_REGISTRATION
FRAMEWORK_ROUTE_TABLE
```

Example:

``` text
Evidence:
CALL

Source:
services/project_service.py:42

Target:
repositories/project_repository.py:44
```

------------------------------------------------------------------------

# 34. Generated Markdown Structure

The final `ROUTES.md` should have this structure:

``` text
# AbhiHub Route Dependency Map

## 1. Overview

## 2. Route Inventory

## 3. Route Discovery Verification

## 4. Dependency Legend

## 5. Route Dependency Maps

### ROUTE-001
...

### ROUTE-002
...

## 6. Global Middleware

## 7. Global Configuration

## 8. Shared Dependencies

## 9. External Services

## 10. Database Dependencies

## 11. Dynamic Dependencies

## 12. Broken Dependencies

## 13. Circular Dependencies

## 14. Orphaned Routes

## 15. Unused Dependencies

## 16. Analysis Limitations

## 17. Final Statistics
```

------------------------------------------------------------------------

# 35. Global Shared Dependency Map

The agent should identify dependencies shared across multiple routes.

Example:

``` text
auth.py
 ├── GET /users
 ├── POST /users
 ├── GET /projects
 ├── POST /projects
 └── DELETE /projects/{id}
```

The Markdown should include:

``` markdown
## Shared Dependencies

| Dependency | Routes | Purpose |
|---|---:|---|
| `middleware/auth.py` | 24 | Authentication |
| `database/session.py` | 31 | Database access |
| `config/settings.py` | 37 | Application configuration |
```

------------------------------------------------------------------------

# 36. Route-to-File Reverse Index

The agent should also generate a reverse lookup.

Example:

``` markdown
## File → Routes

### `services/user_service.py`

Used by:

- `GET /users`
- `GET /users/{id}`
- `POST /users`
- `PUT /users/{id}`

### `database/session.py`

Used by:

- 31 routes
```

This makes impact analysis much easier.

If a developer changes:

``` text
services/user_service.py
```

they immediately know which routes may be affected.

------------------------------------------------------------------------

# 37. Change Impact Analysis

The agent should support a second mode:

``` text
"What routes are affected if I change this file?"
```

Example:

``` text
Changed file:
services/user_service.py
```

Output:

``` text
Potentially affected routes:

GET  /users
GET  /users/{id}
POST /users
PUT  /users/{id}

Total:
4 routes
```

The agent should use the generated dependency graph rather than
rescanning blindly whenever possible.

------------------------------------------------------------------------

# 38. Agent Execution Pipeline

The agent should operate as:

``` text
1. Locate app.py
2. Detect framework
3. Discover application object
4. Discover routers / blueprints
5. Discover all routes
6. Normalize route paths
7. Resolve route handlers
8. Trace handler dependencies
9. Trace transitive dependencies
10. Detect middleware
11. Detect authentication
12. Detect validation
13. Detect database access
14. Detect external services
15. Detect templates/assets
16. Detect configuration
17. Detect environment variables
18. Detect error handlers
19. Detect startup dependencies
20. Detect dynamic dependencies
21. Detect circular dependencies
22. Detect broken dependencies
23. Build dependency graph
24. Verify route completeness
25. Generate Markdown
26. Run consistency checks
27. Regenerate if errors are found
28. Produce final report
```

------------------------------------------------------------------------

# 39. Self-Correction Loop

The route mapping agent should also use a verification loop.

``` text
Generate Route Map
       ↓
Validate
       ↓
Errors?
   ┌───┴───┐
  YES      NO
   │        │
   ▼        ▼
Analyze   Finalize
Error
   │
   ▼
Correct Mapping
   │
   ▼
Validate Again
```

It should continue until:

``` text
Route discovery verified
AND
Dependency references resolve
AND
Line references are valid
AND
Markdown structure is valid
```

or until it reaches a safety limit.

------------------------------------------------------------------------

# 40. Line Verification

After generating the document, the agent should verify every reported
line number.

For each entry:

``` text
File exists?
Line exists?
Referenced symbol exists?
Reference still matches line?
```

Example:

``` text
services/users.py:42
```

must be checked against the actual file.

If the source changes during analysis, the agent must regenerate
affected references.

------------------------------------------------------------------------

# 41. No Hallucinated Paths

The agent must follow this strict rule:

> **Never invent a file path, function, class, route, or line number.**

If something cannot be resolved:

``` markdown
Path:
UNKNOWN

Reason:
Dependency is dynamically loaded through `importlib`.

Confidence:
LOW
```

It is better to report uncertainty than to manufacture a beautiful
fiction.

------------------------------------------------------------------------

# 42. Incremental Updates

The agent should support incremental regeneration.

If only:

``` text
routes/users.py
```

changes, the agent should determine which route mappings are affected.

It can then update:

``` text
ROUTES.md
```

without unnecessarily reprocessing the entire project.

However, a full scan should remain available for verification.

------------------------------------------------------------------------

# 43. Recommended Commands

The agent could expose:

``` bash
route-agent scan
```

Full scan.

``` bash
route-agent verify
```

Verify an existing `ROUTES.md`.

``` bash
route-agent update
```

Update the route map after code changes.

``` bash
route-agent impact path/to/file.py
```

Show routes affected by a file.

``` bash
route-agent route "GET /api/users"
```

Show the dependency chain for a specific route.

``` bash
route-agent audit
```

Perform a complete route/dependency audit.

------------------------------------------------------------------------

# 44. Agent System Prompt

The core instruction should be:

> You are the AbhiHub Route Dependency Mapping Agent.
>
> Your task is to inspect the application beginning at `app.py` and
> produce a complete, evidence-based Markdown map of every possible
> application route and everything required for each route to load and
> execute.
>
> Discover routes through actual framework registration mechanisms,
> including routers, blueprints, included routers, mounted applications,
> decorators, and dynamic registrations where they can be resolved.
>
> For every route, trace the handler and recursively trace relevant
> dependencies.
>
> Record exact file paths and exact line numbers whenever possible.
>
> Distinguish direct, transitive, runtime, conditional, optional, and
> dynamic dependencies.
>
> Include middleware, authentication, authorization, validation,
> database access, external services, configuration, environment
> variables, templates, static assets, startup resources, and error
> handlers when they are relevant to the route.
>
> Never invent a dependency or line number.
>
> Every dependency must have evidence explaining why it is required.
>
> Verify every reported file and line after generating the Markdown.
>
> Verify that all discovered routes are represented in the final
> document.
>
> Detect broken references, orphaned routes, circular dependencies,
> dynamic dependencies, and unused route dependencies.
>
> If something cannot be statically determined, clearly mark it as
> uncertain and explain why.
>
> The final Markdown must be useful to an engineer who needs to
> understand exactly what will break or be affected if a file is
> modified.
>
> Accuracy is more important than completeness claims.
>
> Never hide uncertainty.
>
> The final output is a route dependency map, not a generic project
> overview.

------------------------------------------------------------------------

# 45. Final Output Example

``` markdown
# AbhiHub Route Dependency Map

Generated:
2026-08-15

Source:
`app.py`

Routes:
37

Analysis Confidence:
HIGH

---

## ROUTE-014

### `GET /api/projects/{project_id}`

**Registration**

`app.py:84`

**Handler**

`routes/projects.py:42-68`

**Authentication**

`middleware/auth.py:14-48`

**Authorization**

`services/permissions.py:22-47`

### Dependency Tree

```text
app.py:84
│
├── middleware/auth.py:14-48
│   └── auth/token.py:22-61
│
├── routes/projects.py:42-68
│   ├── schemas/project.py:12-29
│   ├── services/project_service.py:31-67
│   │   ├── repositories/project_repository.py:44-73
│   │   │   ├── models/project.py:7-41
│   │   │   └── database/session.py:18-39
│   │   │
│   │   └── services/cache.py:12-31
│   │
│   └── serializers/project.py:9-28
│
└── errors/project_errors.py:12-34
```

### Required Files

  -----------------------------------------------------------------------------------------------------
  File                                               Lines Type          Required Because Confidence
  -------------------------------------- ----------------- ------------- ---------------- -------------
  `app.py`                                              84 ROUTE         Registers the    HIGH
                                                                         route            

  `middleware/auth.py`                               14-48 AUTH          Validates        HIGH
                                                                         authentication   

  `routes/projects.py`                               42-68 HANDLER       Implements route HIGH
                                                                         behavior         

  `schemas/project.py`                               12-29 VALIDATION    Validates        HIGH
                                                                         request          
                                                                         parameters       

  `services/project_service.py`                      31-67 SERVICE       Implements       HIGH
                                                                         project          
                                                                         retrieval        

  `repositories/project_repository.py`               44-73 REPOSITORY    Queries project  HIGH
                                                                         data             

  `models/project.py`                                 7-41 MODEL         Defines database HIGH
                                                                         model            

  `database/session.py`                              18-39 DATABASE      Provides         HIGH
                                                                         database session 
  -----------------------------------------------------------------------------------------------------

### Database

**Model**

`models/project.py:7-41`

**Repository**

`repositories/project_repository.py:44-73`

**Session**

`database/session.py:18-39`

### External Services

None.

### Environment Variables

  Variable         File                       Purpose
  ---------------- -------------------------- ---------------------
  `DATABASE_URL`   `database/session.py:18`   Database connection

### Error Handling

`errors/project_errors.py:12-34`

Handles:

`ProjectNotFoundError`

### Verification

-   Route registration verified: YES
-   Handler verified: YES
-   File paths verified: YES
-   Line references verified: YES
-   Dependency chain verified: YES

```{=html}
<!-- -->
```

    ---

    # 46. Definition of Done

    The agent is considered successful when:

    ```text
    ✓ Every discoverable route is listed
    ✓ Every route has a unique ID
    ✓ Every route has method + path
    ✓ Every route has registration location
    ✓ Every route has handler location
    ✓ Relevant dependencies are recursively mapped
    ✓ File paths are verified
    ✓ Line numbers are verified
    ✓ Middleware is mapped
    ✓ Authentication is mapped
    ✓ Authorization is mapped
    ✓ Validation is mapped
    ✓ Database dependencies are mapped
    ✓ External services are mapped
    ✓ Configuration is mapped
    ✓ Environment variables are mapped
    ✓ Templates/assets are mapped
    ✓ Error handlers are mapped
    ✓ Dynamic dependencies are flagged
    ✓ Broken dependencies are detected
    ✓ Circular dependencies are detected
    ✓ Orphan routes are detected
    ✓ Confidence is recorded
    ✓ Evidence exists for dependencies
    ✓ Final Markdown passes consistency checks

------------------------------------------------------------------------

# 47. Relationship With the AbhiHub Optimization Agent

This route-mapping agent should become a foundational subsystem of the
previously designed **AbhiHub Code Optimization Agent**.

The relationship should be:

``` text
                    AbhiHub Repository
                           │
                           ▼
                 Route Dependency Agent
                           │
                           ▼
                    ROUTES.md
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
       Optimization Agent          Security Agent
             │                           │
             ▼                           ▼
      Performance Analysis        Route Attack Surface
             │                           │
             └─────────────┬─────────────┘
                           ▼
                    Engineering Agent
                           │
                           ▼
                    Safe Optimization
                           │
                           ▼
                    Test + Measure
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                  KEEP         ROLLBACK
```

The route map therefore becomes an **impact-analysis layer** for the
larger engineering agent.

If a future optimization changes:

``` text
services/project_service.py
```

the optimization agent can immediately query the route map and
determine:

``` text
Affected Routes:
GET  /api/projects/{id}
GET  /api/projects
POST /api/projects
PUT  /api/projects/{id}

Potentially affected:
4 routes
```

This makes the self-correcting optimization loop substantially safer
because the agent knows **what the blast radius of a change is before
making it**.
