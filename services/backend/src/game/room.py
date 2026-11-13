from __future__ import annotations
import copy
import random
import secrets
import time
from .catalog import DEFAULT_CAPACITY, LEGACY_ROOM
from .errors import GameError
from .state import fresh
from . import membership, rounds, answers, scoring, bots, views


class GameRoom:

    def __init__(
        self,
        code,
        name,
        game_state=None,
        created_at=None,
        *,
        catalog,
        clock=None,
        rng=None,
    ):
        self.code = code
        self.name = name
        self.catalog = catalog
        self.state = copy.deepcopy(game_state) if game_state is not None else fresh()
        self.clock = clock or time.time
        self.rng = rng or random.SystemRandom()
        self.created_at = created_at if created_at is not None else self.clock()

    def image_url(self, filename):
        prefix = "/api/uploads" if self.code == LEGACY_ROOM else "/api/uploads/" + self.code
        return prefix + "/" + filename

    def summary(self):
        return views.summary(self)

    def player(self, token):
        p = next((p for p in self.state["players"] if p["token"] == token), None)
        if not p:
            raise GameError(401, "Подключись к игре заново")
        return p

    def leader(self):
        humans = [p for p in self.state["players"] if not p.get("bot")]
        return next(
            (p for p in humans if not p.get("waiting")), humans[0] if humans else None
        )

    def host(self, token):
        owner = self.leader()
        if not owner or not secrets.compare_digest(token or "", owner["token"]):
            raise GameError(403, "Это действие доступно организатору на телефоне")

    def current(self):
        return self.state["rounds"][self.state["index"]]

    def capacity(self):
        return self.state.get("capacity", DEFAULT_CAPACITY)

    def active(self):
        return [p for p in self.state["players"] if not p.get("waiting")]

    def begin_round(self):
        return rounds.begin_round(self)

    def accept_answer(self, r, p, text, image=None, power=False, partner=None):
        return answers.accept_answer(self, r, p, text, image, power, partner)

    def caption_assignment(self, r, player_id):
        return answers.caption_assignment(self, r, player_id)

    def reveal(self):
        return scoring.reveal(self)

    def advance_round(self):
        return rounds.advance_round(self)

    def progress(self):
        return rounds.progress(self)

    def bot_step(self):
        return bots.bot_step(self)

    def view(self, token):
        return views.view(self, token)

    def join(self, name):
        return membership.join(self, name)

    def leave(self, token):
        return membership.leave(self, token)

    def configure(self, token, values, supplied):
        return membership.configure(self, token, values, supplied)

    def add_bots(self, token):
        return membership.add_bots(self, token)

    def remove_player(self, token, player_id):
        return membership.remove_player(self, token, player_id)

    def start(self, token):
        return rounds.start(self, token)

    def next(self, token, round_id, force=False):
        return rounds.next(self, token, round_id, force)

    def lobby(self, token):
        return rounds.lobby(self, token)

    def answer(self, token, body, *, image_allowed=False):
        return answers.answer(self, token, body, image_allowed=image_allowed)

    def vote(self, token, body):
        return answers.vote(self, token, body)

    def generate(self, token, body):
        return answers.generate(self, token, body)

    def apply_image(
        self, round_id, owner, job_id, *, image=None, error=None, moderated=False
    ):
        return answers.apply_image(
            self, round_id, owner, job_id, image=image, error=error, moderated=moderated
        )
