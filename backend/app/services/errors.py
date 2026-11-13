"""Błędy domenowe. main.py zamienia je na odpowiedzi HTTP (404 / 422 / 502)."""


class NotFoundError(Exception):
    pass


class IncompleteError(Exception):
    """Spotkanie nie jest gotowe do obliczeń — `problems` trafia do UI."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class ExternalServiceError(Exception):
    """Usługa zewnętrzna (Geoapify / OSRM) nie odpowiedziała poprawnie."""


class CommandError(Exception):
    """Polecenia nie da się wykonać (np. nieznana osoba, limit 6). Nic nie zapisujemy.

    `needs_answer=True` oznacza niejednoznaczność — UI pokazuje to jako pytanie."""

    def __init__(self, message: str, needs_answer: bool = False):
        super().__init__(message)
        self.needs_answer = needs_answer
