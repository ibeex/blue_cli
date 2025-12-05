# Architecture

Detailed architecture documentation for Blue CLI.

## Service Layer Pattern

All services inherit from `BluesoundBaseClient` in `base_client.py`, which provides:

- `_get(endpoint)` - HTTP GET for BlueOS API queries
- `_post(endpoint, params)` - HTTP POST for control commands
- `_parse_xml(response)` - XML to Python dict via xmltodict
- `_query(data, jmespath_expr)` - JMESPath queries on XML data

Services extending the base client:

- `usb_service.py` - Local USB music library (aliased as BlueSound)
- `tidal_service.py` - Tidal streaming integration
- `playlist_service.py` - Playlist management
- `ai_service.py` - OpenAI-powered music recommendations

## Key Patterns

### Command Aliasing

`blue_cli.py` uses `AliasedGroup` class for partial command matching. Users can type partial commands like `b p` instead of `blue_cli play`.

### Dependency Injection

The `@with_blue_service` decorator injects service instances into Click commands, handling initialization and cleanup.

### Caching Strategy

Search results cached for 24 hours using `diskcache` library:

- Cache location: `~/.cache/blue/`
- Prevents redundant API calls
- Improves search performance

### FZF Integration

`pyfzf` is a required dependency for interactive music selection. Used in search commands to present results and capture user selection.

### Volume Control

Gradual volume stepping when changes exceed 5 units to prevent audio shock:

```python
# Changes >5 step gradually
if abs(target - current) > 5:
    step_volume(current, target)
```

### AI Music Filtering

AI recommendations exclude rap/hip-hop genres. Implemented in `ai_service.py` via prompt filtering.

## API Integration

### BlueOS XML API

- Base URL: `http://{host}:{port}/`
- All endpoints return XML responses
- `/Services` endpoint documents available API endpoints

### Request Methods

- **GET** - Query operations (status, library, search)
- **POST** - Control operations (play, pause, volume)

### Response Parsing

1. HTTP response -> XML string
2. xmltodict -> Python dict
3. JMESPath -> Extract nested data

Example:

```python
response = self._get("/Status")
data = self._parse_xml(response)
volume = self._query(data, "status.volume")
```

## Configuration Management

Configured via `config.py`:

- `DEFAULT_HOST` - BlueOS host (default: `192.168.88.15:11000`)
- `CACHE_DIR` - Cache location (`~/.cache/blue/`)
- `MEDIA_LOCATION` - USB mount path for local music
- OpenAI API key: Environment variable or LLM keys file

## Error Handling

Base client provides common error handling:

- Connection errors -> User-friendly messages
- XML parsing errors -> Graceful fallbacks
- API errors -> Status code interpretation
