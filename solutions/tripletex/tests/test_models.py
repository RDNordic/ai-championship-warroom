from __future__ import annotations

import pytest
from pydantic import ValidationError

from tripletex_agent.client import TripletexClient
from tripletex_agent.models import SolveRequest


def test_solve_request_parses_and_normalizes_base_url() -> None:
    request = SolveRequest.model_validate(
        {
            "prompt": "Opprett en ansatt",
            "files": [
                {
                    "filename": "note.txt",
                    "content_base64": "aGVsbG8=",
                    "mime_type": "text/plain",
                }
            ],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2/",
                "session_token": "secret-token",
            },
        }
    )

    assert request.tripletex_credentials.base_url == "https://tx-proxy.ainm.no/v2"
    assert request.tripletex_credentials.basic_auth_username() == "0"
    assert request.tripletex_credentials.basic_auth_password() == "secret-token"


def test_solve_request_rejects_blank_prompt() -> None:
    with pytest.raises(ValidationError):
        SolveRequest.model_validate(
            {
                "prompt": "   ",
                "tripletex_credentials": {
                    "base_url": "https://tx-proxy.ainm.no/v2",
                    "session_token": "secret-token",
                },
            }
        )


def test_client_select_fields_joins_non_empty_values() -> None:
    assert TripletexClient.select_fields("id", "", "name") == "id,name"
