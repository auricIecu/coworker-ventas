import re

from mostrador.domain import Actor, DomainError, SearchIntent


class DemoIdentity:
    def authenticate(self, token: str) -> Actor:
        roles = {"demo-clerk": "clerk", "demo-supervisor": "supervisor", "demo-viewer": "viewer"}
        if token not in roles:
            raise DomainError("invalid_credentials", 401)
        return Actor(token, roles[token])


class KeywordAssistant:
    """Deterministic demo, not an LLM. Only extracts a commercial search term."""

    def interpret(self, message: str) -> SearchIntent:
        query = re.sub(r"^(buscar|busca|consultar)\s+", "", message.strip(), flags=re.I)
        return SearchIntent(query)
