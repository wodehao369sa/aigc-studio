# Provider plugins

Each provider is a self-contained Python package under `app/providers/<provider_id>/`.
The registry scans this directory at startup and imports `<provider_id>/definition.py`,
which must expose:

- `PROVIDER_DEFINITION`: a `ProviderDefinition` describing the provider id, label,
  default base URL, supported capabilities and model presets.
- `create_adapter`: a callable receiving a `ProviderRuntime` and returning a
  `ProviderAdapter`.

Adding a provider therefore means adding one directory; removing a provider means
deleting it and calling `POST /api/settings/providers/reload` (or restarting).

## Layout

```text
app/providers/<provider_id>/
  __init__.py
  definition.py     # PROVIDER_DEFINITION + create_adapter
  adapter.py        # validate / submit / get_status
  models.py         # optional model presets
```

## Adapter contract

```python
class ProviderAdapter(ABC):
    provider_id: str

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        """Return human-readable validation errors; empty means valid."""

    async def submit(self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime) -> ProviderTaskRef:
        """Create the upstream task.

        Synchronous providers put the finished payload in
        ``ProviderTaskRef.result_urls`` (media) or ``result_text`` (text) and the
        task service persists it immediately.
        """

    async def get_status(self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime) -> ProviderStatus:
        """Normalize the upstream task state to running/succeeded/failed."""
```

## Reference runtime

`ProviderRuntime` carries `base_url`, `api_key`, `timeout`, `public_base_url`
and a `media` reader. Never log `api_key`. Reference images should be passed to
the upstream as `AssetInput.public_url`; if it is empty, fall back to a Base64
data URI built from `runtime.media.read_bytes(...)`.

## Rules

- Keep all upstream request/response mapping inside the adapter. Task, asset and
  API layers must never branch on a provider name.
- Model presets live in the provider package so the settings page can offer them
  without hard-coding a catalog in the frontend.
- Return readable Chinese validation errors; they are shown to the user as-is.
