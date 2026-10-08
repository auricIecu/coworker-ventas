import json

import pytest

from mostrador import bedrock
from mostrador.domain import DomainError


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)

    def converse(self, **kwargs):
        assert kwargs["modelId"] == "test-model"
        assert kwargs["system"] and kwargs["messages"]
        return next(self.responses)


def response(value, stop="end_turn"):
    return {
        "output": {"message": {"content": [{"text": json.dumps(value)}]}},
        "stopReason": stop,
        "usage": {"inputTokens": 10, "outputTokens": 10},
    }


def test_converse_parses_json_and_spaces_requests_without_retry():
    clock = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    client = Client([response({"items": []}), response({"items": []})])
    model = bedrock.BedrockInterpreter(
        client=client, model_id="test-model", clock=lambda: clock[0], sleep=sleep
    )
    assert model.infer({"conversations": []}) == {"items": []}
    assert model.infer({"conversations": []}) == {"items": []}
    assert sum(sleeps) >= 1


def test_nova_json_code_fence_is_unwrapped_without_accepting_surrounding_prose():
    wrapped = response({"items": []})
    wrapped["output"]["message"]["content"][0]["text"] = '```json\n{"items": []}\n```'
    model = bedrock.BedrockInterpreter(client=Client([wrapped]), model_id="test-model")
    assert model.infer({}) == {"items": []}


@pytest.mark.parametrize(
    "reply",
    [
        response({}, "max_tokens"),
        {"output": {"message": {"content": [{"text": "not json"}]}}, "stopReason": "end_turn"},
        {
            "output": {"message": {"content": [{"text": "Extra text ```json\n{}\n```"}]}},
            "stopReason": "end_turn",
        },
    ],
)
def test_invalid_or_truncated_output_does_not_become_a_recommendation(reply):
    model = bedrock.BedrockInterpreter(client=Client([reply]), model_id="test-model")
    with pytest.raises(DomainError, match="model_invalid_response"):
        model.infer({})


def test_expired_aws_credentials_return_safe_error_without_retry():
    from botocore.exceptions import ClientError

    class ExpiredClient:
        calls = 0

        def converse(self, **kwargs):
            self.calls += 1
            raise ClientError(
                {"Error": {"Code": "ExpiredTokenException", "Message": "private SDK detail"}},
                "Converse",
            )

    client = ExpiredClient()
    model = bedrock.BedrockInterpreter(client=client)
    with pytest.raises(DomainError, match="^aws_session_expired$"):
        model.infer({})
    assert client.calls == 1
