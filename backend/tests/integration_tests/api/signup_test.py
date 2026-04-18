import pytest

from bracket.utils.http import HTTPMethod
from bracket.utils.types import JsonDict
from tests.integration_tests.api.shared import send_request


@pytest.mark.asyncio(loop_scope="session")
async def test_signup_unknown_token_returns_404(
    startup_and_shutdown_uvicorn_server: None,
) -> None:
    response: JsonDict = await send_request(
        HTTPMethod.GET,
        "signup/nonexistent-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    assert response == {"detail": "Signup link is invalid or signup is closed"}
