"""The api for the real-uvicorn tests: counts the body bytes the app pulls (GET /__read).

`/api/intake/probe` has the upload's limits and a body parameter, which makes FastAPI read the
body before resolving the session dependency."""

from typing import Annotated

from fastapi import Body, Depends

from mona.api.deps import current_session
from mona.app import create_app

api = create_app()


@api.post("/api/intake/probe", include_in_schema=False)
async def intake(
    data: Annotated[bytes, Body(media_type="application/octet-stream")],
    _: Annotated[object, Depends(current_session)],
) -> dict:
    return {"bytes": len(data)}


read = 0


async def app(scope, receive, send):  # noqa: ANN001, ANN201
    global read
    if scope["type"] == "http" and scope["path"] == "/__read":
        body = str(read).encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})
        return

    async def counted():  # noqa: ANN202
        global read
        message = await receive()
        if message["type"] == "http.request":
            read += len(message.get("body", b""))
        return message

    await api(scope, counted if scope["type"] == "http" else receive, send)
